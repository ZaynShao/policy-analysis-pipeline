# Codex 交接：评论反向发现补采(commentary reverse-discovery backfill)

## 背景 / 要治的根因

L1 现状:**评论发现「我们缺某政策」的信号生成后被丢弃,没变成采集动作**——死胡同。
- 当前管道里 `related_policy` 只有 `route_interpretations.py:174` 一处写,且**只对已采政策做标题匹配**;未命中 → 留空、丢弃。
- `commentary_signals` 对空 `related_policy` 的评论**直接跳过**(实测"42 篇无关联跳过")。
- 投影层只把已采引用作**软引用**进 DB,悬挂的被动等;**没有任何组件把"被评论引用但未采的政策"喂回 L1 抓取**(grep `enqueue/补采/backfill/uncollected` 全空)。

**本任务**:建一条**评论反向发现补采**——从评论引用里发现"被讨论但未采"的政策,喂回现有 fetch→gate→ingest;关不住的(仅标题)进 review pool 交人(B14)。**相关性闸保住能源范围**(资管中心类金融政策不因被提及就采)。

## 纪律(红线)

- **TDD 红先行**,红绿分 commit。沿用 `tests/l1_collect/`,**mock 网络/文件边界**(fetch/gate/ingest/requests 全 mock),不打真网、不读真 vault。
- **不写生产 vault**:`--apply` 的 ingest 走现有 `ingest_extracted(out_dir=...)`,测试里 out_dir 指 tmp;默认 **dry-run**。
- 候选队列写**仓内** `state/l1_backfill/from_commentary.jsonl`(派生层,不写 raw)。
- 只新增/改:`scripts/l1_collect/commentary_backfill.py`(新)、`scripts/l1_collect/review_pool.py`(加一个 kind 的 VERDICTS 条目)、`tests/l1_collect/` 对应测试。**既有未跟踪文件不碰;不 push。**
- `docs/handoffs/2026-06-15-codex-l1-commentary-backfill.md` 已由上游放好并提交,**别改它**。
- 滑坡自审:复用现有 dedup/gate/ingest/KEYWORDS,**不另造**抓取/分类/去重逻辑。

**分支**:当前 worktree 已在 `feat/l1-commentary-backfill`(从 origin/main 切),**不要再建/切分支**。

## 复用的现成件(别重写)

- `scripts/l1_collect/dedup.py` → `DedupIndex.from_vault_policies(policies_dir)`,有 `.url_hashes` / `.title_hashes` / `.offnum_hashes`(判"已采")。
- `scripts/l1_collect/route_interpretations.py` → `build_title_index(skip_paths=set(), vault_root=...)` 返回 `[(norm_title, pid, raw_title)]`;`_normalize(s)` 规范化标题;`match_related(ref_name, index)` 双向 containment 匹配。
- `scripts/l1_collect/step2_scan.py` → `KEYWORDS`(能源相关性词表,判范围)。
- `scripts/l1_collect/policy_gate.py` → `gate_one(ref, url, title, body_head, llm_fn)`(政策 vs 非政策分类,已含 review_queue)。
- `scripts/l1_collect/step4_fetch.py` → `fetch_candidates(cand_file, fetch_dir, err_log)`;`step4_5_extract.extract_all`;`step5_ingest.ingest_extracted(ext_dir, log, out_dir=...)`。复用整条或调底层 `fetcher`,你择优,**但别新造**。
- `scripts/l1_collect/review_pool.py` → `append(entry)` 按 `(kind, ref)` 去重;`VERDICTS` dict(每 kind 的人工裁决枚举)。

## 改动

### A · `commentary_backfill.py`(新)

```python
@dataclass
class PolicyRef:
    title: str | None          # 《》内政策名(若有)
    url: str | None            # 正文里的 gov 政策 URL(若有)
    source_commentary: str     # 来源评论文件名
    business_tag: str          # 来源评论 business_tag(power/gas/charging/cross)
    context: str               # 链接/标题周边 ±100 字(供相关性判断)

GOV_POLICY_URL_RE = ...   # https?://<host>.gov.cn/... ,排除纯首页/检索页
TITLE_RE = re.compile(r"《([^》]{6,60})》")

def extract_policy_refs(md_text: str, source: str) -> list[PolicyRef]:
    """从一篇评论(frontmatter+body)抽 gov 政策 URL + 《》标题,带 business_tag/context。"""

def is_in_scope(ref: PolicyRef) -> bool:
    """相关性闸:ref.title 或 ref.context 含 step2_scan.KEYWORDS 任一 → True。
    挡掉资管中心类金融政策(标题无能源词)。"""

def is_already_collected(ref: PolicyRef, dedup, title_index) -> bool:
    """URL 命中 dedup.url_hashes,或 title 经 match_related 命中 title_index → 已采。"""

def find_backfill_candidates(commentaries_dir: Path, dedup, title_index) -> list[PolicyRef]:
    """遍历 commentaries/*.md → 抽 refs → 去已采 → 过相关性闸 → 按 (url or norm title) 去重。"""

def run_backfill(commentaries_dir: Path, vault_policies: Path, *,
                 dry_run: bool = True, llm_fn=None, state_dir: Path = ...) -> dict:
    """build dedup+title_index → find_backfill_candidates → 候选写
    state/l1_backfill/from_commentary.jsonl。
    not dry_run:
      - 有 URL 的候选 → fetch → gate_one → pass 且 fetched title 仍过相关性闸 → ingest_extracted(out_dir=vault_policies);
      - 仅标题的候选 → review_pool.append(kind='reverse_discovery', ref=norm_title, ...)。
    返回 {scanned_commentaries, candidates, url_collected, queued_title_only, dropped_irrelevant}。"""
```

CLI `main()`:`--commentaries-dir`、`--vault-policies`、`--apply`(缺省 dry-run)、`--state-dir`。dry-run 打印 stats + 候选前若干条。

### B · `review_pool.py`

`VERDICTS` 加 `reverse_discovery` 条目:裁决枚举 `("collect", "drop")`(collect=补采该政策 / drop=丢弃)。其余不动。

## 测试(红先行,mock)

新建 `tests/l1_collect/test_commentary_backfill.py`:
- `extract_policy_refs`:给一篇含 `《关于推动X的实施意见》` + 一个 `https://fgw.shandong.gov.cn/.../t.html` 的评论 → 抽出 1 title + 1 url,带 context/business_tag。
- **相关性闸(关键)**:`is_in_scope` 对"关于深化上海全球资产管理中心建设的若干意见"(无能源词)→ **False**;对含"光伏/电力/充电"的 → True。
- `is_already_collected`:url 在 `dedup.url_hashes` → True;title 经 `match_related` 命中 index → True;都不中 → False。
- `find_backfill_candidates`:构造 3 篇评论(1 已采 url、1 资管中心无关、1 新的能源政策)→ 只返 1 个候选(新能源那条);去重 OK。
- `run_backfill` dry-run:写 `from_commentary.jsonl`,**不**调 fetch/ingest。
- `run_backfill` apply:URL 候选 → mock fetch+gate(pass)+ingest 被调;仅标题候选 → `review_pool.append` 被调(kind=reverse_discovery)。
- apply 且 gate 判非政策 / fetched title 失相关性 → **不** ingest。
- 回归:`pytest -q` 全绿。

## 验证

```
python3 -m pytest tests/l1_collect/test_commentary_backfill.py -q   # 全绿
python3 -m pytest -q                                                # 不回退
python3 -m scripts.l1_collect.commentary_backfill --commentaries-dir <tmp> --dry-run   # 冒烟不崩
```

## 回报

stdout:分支、各 commit(红/绿)、`pytest -q` 全量数字、`commentary_backfill.py` 关键函数签名、新增 review_pool kind。无需 report 文件。

## ops(不在本任务)

- `--apply` 需网络(fetch)+ LLM(gate);无微信地理约束,国内/东京均可。
- cron:低频跑 `run_backfill --apply`(或先 dry-run 出候选交人),与渠道 reprobe 同属"L1 覆盖自愈"。待 S2 cutover 后接。
- 与 `feat/l1-channel-lifecycle`(渠道生命周期闭环)是一对:渠道闭环治"相关内容被渠道挡住",本线治"评论替我们发现了缺口政策"。
