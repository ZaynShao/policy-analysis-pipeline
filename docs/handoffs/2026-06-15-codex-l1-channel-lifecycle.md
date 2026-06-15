# Codex 交接：L1 渠道生命周期闭环 + 省能源局/NEA监管机构建模

**触发**：2026-05 能源月刊交叉核对发现 3 条省级能源政策 ABSENT（山东光伏意见、吉林新能源方案、山西电力中长期细则）。诊断见 `docs/2026-06-15-L1省级能源覆盖缺口-诊断与机制设计.html`。

**根因（一句话）**：渠道层硬伤——(A) 渠道生命周期无闭环：发现是手动 oneshot、验证是单次首探、晋升是写死快照，常驻增量只扫已验证渠道 → 首探失败的渠道永久变暗（31 省验证过的能源局 = 0）；(B) 省能源局非一等发现目标（registry 冷启动循环）；(C) 国家能源局派出监管机构（发电力市场细则那类）整个没建模。

**本任务做三件事，治这三层。三件相互独立，可分 commit。**

**用户已拍的决策**：候选→验证晋升做成 **probe-ok 自动**（"是不是真列表页"是确定性 probe 信号，机构核验歧义才留池给人/B14）。

---

## 纪律（红线）

- **TDD 红先行**，红绿分 commit。沿用 `tests/l1_collect/`，**mock 网络**（Tavily/firecrawl/LLM/requests 全 mock，不打真网）。
- **不写生产 vault**；不改 `0_raw/`。catalog 写 `state/T1_channels/channel_catalog.yaml`（仓内 state，provenance）。
- **dry-run 默认**：复探/发现脚本默认 `--dry-run`，apply 需显式开关。
- 许改文件：`scripts/l1_collect/channel_discovery.py`、新建 `scripts/l1_collect/channel_reprobe.py`、`scripts/_oneshot/expand_channels_l1.py`、对应测试，以及 vault 内 `00 背景资料/渠道目录.md`（仅追加 NEA 段，dry-run 给 diff 等用户过）。**既有未跟踪文件不碰；不合 main 不 push。**
- 滑坡自审：改的是**规则/目标生成**（无条件网格、机构大类），不是 per-domain 特例。

**分支**：`feat/l1-channel-lifecycle`（从 main 最新起）。

---

## 改动 ① 候选自愈复探 + probe-ok 自动晋升（治 A，主修）

新建 `scripts/l1_collect/channel_reprobe.py`。复用现有 `discover_one`（它已含 firecrawl 兜底 + Tavily/LLM 重找列表页 + `_institution_match`），**不重写 probe 逻辑**。

```python
from datetime import datetime, timezone, timedelta
from .channel_catalog import load_catalog, save_catalog, Channel, ChannelStatus
from .channel_discovery import discover_one
from . import review_pool

def reprobe_candidate(ch: Channel, *, today: str) -> tuple[Channel, str]:
    """对单个候选重跑 discover_one。返回 (更新后 ch, outcome)。
    outcome ∈ {"promoted","ambiguous","still_candidate"}。"""
    target = {"city": ch.city, "province": ch.province, "level": ch.level,
              "city_code": ch.city_code, "channel_type": ch.channel_type,
              "root_domain": ch.root_domain or None}
    fresh = discover_one(target)
    if fresh is None:
        return ch, "still_candidate"
    ch.last_probed_at = fresh.last_probed_at
    ch.probe_result = fresh.probe_result
    if fresh.list_url:
        ch.list_url = fresh.list_url
    if fresh.root_domain:
        ch.root_domain = fresh.root_domain
    if fresh.status == ChannelStatus.验证:
        ch.status = ChannelStatus.验证                       # ← probe-ok + 机构核验过 = 自动晋升
        _stamp(ch, f"auto-promoted-{today}-probe-ok")
        return ch, "promoted"
    if fresh.probe_result == "ok":                            # probe ok 但 discover_one 仍判候选 = 机构核验歧义
        review_pool.append(review_pool.candidate_entry(ch))   # ← 留候选 + 进池给人(B14)
        return ch, "ambiguous"
    return ch, "still_candidate"

def reprobe_candidates(catalog, *, only_types=None, limit=None, dry_run=True, today=None):
    cands = [c for c in catalog if c.status == ChannelStatus.候选]
    if only_types:
        cands = [c for c in cands if c.channel_type in only_types]
    if limit:
        cands = cands[:limit]
    promoted = ambiguous = 0
    for c in cands:
        _, outcome = reprobe_candidate(c, today=today)
        promoted += outcome == "promoted"
        ambiguous += outcome == "ambiguous"
    if not dry_run:
        save_catalog(catalog, CAT)
    return {"scanned": len(cands), "promoted": promoted, "ambiguous": ambiguous}
```

- `_stamp(ch, note)`：幂等地把 note 追到 `ch.notes`（参 `promote_checkpoint_channels.py` 的 NOTE 写法）。
- `today`：CST `date` 串，从 CLI/调用方传入（**别在脚本里 `datetime.now()` 写死**，便于测试）。
- CLI `main()`：`--only-types 能源局,发改委,能源监管`、`--limit N`、`--apply`（缺省 dry-run）、`--today`。
- **安全性**（写进 docstring）：自动晋升只在 `discover_one` 返回"验证"（= probe ok **且** 机构核验过）时发生；下游 `scan` 仍按 KEYWORDS 过标题、`policy_gate` 仍逐篇 LLM 判类，错渠道只少命中、不灌脏库。

> 首跑（operator 带凭据，`--apply`）即把 754 候选全量自愈，一次性回收山东/吉林。此后 cron 低频保鲜（接线见末尾"ops"，本任务不动 cron）。

## 改动 ② 省能源局升一等目标（治 B）

`channel_discovery.py` 加无条件网格，仿 `commerce_market_targets`：

```python
def province_energy_targets() -> list:
    """31 省 × {发改委, 能源局} 无条件目标(root_domain=None,交发现解析)。
    绕开 province_targets_from_registry 的'要先有能源条目才生成能源目标'冷启动循环。"""
    out = []
    for prov, code in _PROV_CODE.items():
        for ctype in ("发改委", "能源局"):
            out.append({"city": prov, "province": prov, "level": "省",
                        "city_code": f"{code}0000", "channel_type": ctype,
                        "root_domain": None})
    return out
```

`expand_channels_l1.py` 的 `province` level 改为 `province_targets_from_registry(REG)` ∪ `province_energy_targets()`，按 `(province, channel_type)` 去重，**优先保留带已知 root_domain 的那条**（registry 暖启动域名不丢）。

## 改动 ③ NEA 派出监管机构建模（治 C）

`channel_discovery.py`：

```python
NEA_REGIONAL = [   # 6 区域监管局(域名稳定,交发现解析)
    "国家能源局华北能源监管局", "国家能源局东北能源监管局", "国家能源局西北能源监管局",
    "国家能源局华东能源监管局", "国家能源局华中能源监管局", "国家能源局南方能源监管局",
]
# 省级监管办 roster:从国家能源局官网"派出机构"目录核对后填(本任务先填 immediate cases,
# 注意并非 31 省都有独立监管办——部分省由区域监管局直管)。
NEA_PROVINCE_OFFICES = [
    ("山西省", "国家能源局山西监管办公室"),
    ("山东省", "国家能源局山东监管办公室"),
    # … 其余按官网目录补；缺的留待发现/池反哺
]

def nea_regulatory_targets() -> list:
    out = [{"city": n, "province": "国家", "level": "国家", "city_code": "000000",
            "channel_type": "能源监管", "root_domain": None} for n in NEA_REGIONAL]
    for prov, office in NEA_PROVINCE_OFFICES:
        out.append({"city": office, "province": prov, "level": "省",
                    "city_code": f"{_PROV_CODE[prov]}0000",
                    "channel_type": "能源监管", "root_domain": None})
    return out
```

- `_INST_DOMAIN_MARKERS` 加：`"能源监管": ("nea", "dpc")`，让 `nea.gov.cn` 族子域（如 `shanxi.nea.gov.cn`）能过 `_institution_match`（`_area_match` 命不中省拼音段，必须靠 marker）。
- `expand_channels_l1.py` 加 `DISCOVER_LEVELS` 取值 `nea_regulatory` → `targets += nea_regulatory_targets()`。
- `00 背景资料/渠道目录.md`：追加一段 `## 国家能源局派出监管机构（能源监管）`，列 6 区域监管局 + 已知省监管办，注明"域名由发现解析、命中后回填"。**dry-run 出 diff 给用户过再落。**
- （可选，低风险）`step2_scan.py` 的 `KEYWORDS` 补 `电力市场`、`中长期`、`并网`、`辅助服务`——提高能源监管线精度；不补也不漏这 3 条（`电力`/`现货市场` 已在）。

---

## 测试（红先行，mock 网络）

新建 `tests/l1_collect/test_channel_reprobe.py`：

- **关键回归（红）**：构造 status=候选 的 Channel，mock `discover_one` 返回 status=验证 → `reprobe_candidate` 应置"验证"且打 `auto-promoted-…-probe-ok` note（现状无此函数 = 红）。
- mock `discover_one` 返回 候选+`probe_result="ok"`（机构歧义）→ ch 仍候选 + `review_pool.append` 被调用一次（断言 mock 调用）。
- mock 返回 候选+`probe_result="http_error"` → 仍候选、**不**进池、刷新 `last_probed_at`。
- `reprobe_candidates(dry_run=True)` **不**调 `save_catalog`；`dry_run=False` 调一次。
- `only_types` / `limit` 过滤正确；统计 `{scanned,promoted,ambiguous}` 准。
- `_stamp` 幂等(重跑不重复追 note)。

`tests/l1_collect/test_channel_discovery.py` 扩：

- `province_energy_targets()`：返 62 条(31×2)，每省含发改委+能源局，root_domain 均 None。
- `nea_regulatory_targets()`：含 6 区域监管局(level=国家)；省监管办 level=省、channel_type=能源监管、city_code 对。
- `_institution_match("shanxi.nea.gov.cn", {"channel_type":"能源监管",...})` → True；`_institution_match("fgw.shandong.gov.cn", {"channel_type":"能源监管",...})` → False(非 nea 域不误绑)。
- 回归：现有 channel_discovery 测试不破。

---

## 验证

```
python3 -m pytest tests/l1_collect/test_channel_reprobe.py tests/l1_collect/test_channel_discovery.py -q   # 全绿
python3 -m pytest -q                                                                                       # 不回退
# dry-run 冒烟(operator 带凭据时;无凭据则 discover_one 内部降级,验证不崩)
python3 -m scripts.l1_collect.channel_reprobe --only-types 能源局,发改委 --limit 5 --today 2026-06-15
```

## 回报

stdout：分支、各 commit（红绿）、pytest 数字、三处改动的关键函数签名、`渠道目录.md` 的 NEA 段 diff（待用户过）。无需 report 文件。

## ops（不在本任务，记给 operator）

- 凭据：`TAVILY_API_KEY` + `FIRECRAWL_API_KEY` + LLM(`OPENAI_BASE_URL`/`OPENAI_API_KEY`)。发现/复探**无微信地理风控约束**（与评论线不同），国内/东京节点均可。
- 首跑：`expand_channels_l1`（`DISCOVER_LEVELS=province,nea_regulatory`）补全目标 → `channel_reprobe --apply` 自愈 754 候选。
- cron：低频（如每周）跑 reprobe 保鲜；待 S2 W4 policy 线 cutover 后接（现 policy `run_incremental` cron 仍注释）。
