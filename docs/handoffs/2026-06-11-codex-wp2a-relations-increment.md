# Codex 交接：WP-2a ③关系族增量编排器（代码部分，本地 TDD，不碰服务器）

**背景**：③ 关系层 2026-06-06 全量重建后冻结（canonical 1138 边 = HPR_ 615 直并 + SRC_ 523 语义 accepted）。架构裁决（用户）：**增量制**——新政策只和存量匹配，LLM 成本有界；③-D 保持确定性全量重生（不硬造增量边集）。本包做编排器代码 + apply 步；部署/补课跑批是 WP-2b。**不碰服务器、不动 cron、不合 main、不 push。**

**既有机件事实（已核实，直接 import 复用，不复制代码）**：
- ③-B：`scripts.analysis_high_precision_relations.run` `preview --vault --state`，全量 regex 数秒，产 `high_precision_relation_candidates.jsonl`（行含 from/to/rel/doc_number/candidate_id…以源码为准）。
- ③-C 内件：`scripts.analysis_semantic_relations` 的 `loaders.load_policy_views` / `loaders.load_hpr_basis_pairs` / `candidates.generate_candidates` / `judge.judge_candidate` / `program_gate.check_candidate_row` / `program_gate.partition_by_decision`；judge client 用 `OpenAICompatClient`（见该模块 main 的构造方式）。**生成候选无 LLM，judge 才花钱。**
- ③-D：`scripts.analysis_relation_views.run.run_preview(vault, sem_path, hpr_path, out_root)`——合并→滤 dangling→去重→写 `relations_canonical.jsonl` + `_index_by_policy.json` + `_index_by_policy/`（_rev 页，带安全闸）。**apply-to-vault 不在该模块 = 本包要补的步。**
- 6/6 语义 accepted 种子：`state/node3c/sem_preview_20260606/accepted_clean_final.jsonl`（537 行，本地存在）。
- vault 现状：`1_extracted/relations/` 下就是 canonical + _index_by_policy.json + _index_by_policy/ 三件。

**纪律（红线，同 WP-1a）**：主 checkout 工作、切分支 `wp2/relations-increment`、别条线未跟踪文件绝不碰、TDD 红绿分 commit（**上次 WP-1a 红绿挤单 commit 被审计记偏差，这次必须分开**）、凭据无涉、完成后停在分支写报告等审计。

## Task 1 · 种子文件入 git（数据 lineage）

```bash
cp state/node3c/sem_preview_20260606/accepted_clean_final.jsonl state/node3c/sem_accepted_20260606_seed.jsonl
git add state/node3c/sem_accepted_20260606_seed.jsonl
```
（state/node3c 已有 golden/ 等 git-tracked 先例；该文件是 537 行 judged 记录，不可再生，必须进 lineage。）

## Task 2 · `scripts/service/relations_increment.py`（编排器）

状态文件（全在 `--state-dir`，即 VPS `/state`）：
- `relations_pid_ledger.json`：`{"covered": [pid,…], "updated_at": iso}`——已覆盖 pid 集。
- `sem_accepted_cumulative.jsonl`：累积语义 accepted（部署时由种子初始化；每轮 append）。
- `relations_judged_ledger.jsonl`：append-only，每行 `{"candidate_id","decision","ts"}`——防重判。

纯函数（TDD 核心）：
```python
def select_new_pids(tracked_pids: list[str], ledger: dict) -> list[str]
    # tracked − covered,保序

def filter_increment_candidates(cands: list[dict], new_pids: set[str], judged_ids: set[str]) -> list[dict]
    # (from∈new or to∈new) and candidate_id∉judged。字段名以 candidates.py 实际产出为准,实现前先读源码核对

def check_apply_gates(out_root: Path, vault_rel_dir: Path, min_keep_ratio: float = 0.8) -> str | None
    # None=过闸;否则返回拒绝原因:
    # ① out_root 三件齐且 canonical 非空、adjacency 可解析
    # ② 新 canonical 边数 >= 旧边数 × min_keep_ratio(防全量重生意外塌缩;旧文件不存在则跳过该项)
```

子命令：
1. `init-ledger --vault V --state-dir S --as-of-commit SHA`：
   `git -C V archive SHA 0_raw/policies | tar -x -C <tmp>` → 正则抽 frontmatter `id:` → 写 ledger。打印 `{"covered": N}`。
2. `run --vault V --state-dir S --judge-model M --judge-provider openai [--dry-run]`：
   a. ③-B 全量 preview → state（subprocess 或函数调用，以现成入口为准）。
   b. `select_new_pids`（tracked pids 取自 ③-B 已加载的语料或 git ls-files，与 ③-B 同口径）→ 空则打印 `{"new_pids":0}` 直接 exit 0（**ledger 也不动**）。
   c. ③-C 内件：load views + basis → generate_candidates（全量,免费）→ `filter_increment_candidates` → program_gate → 逐条 judge → accepted **append** 进 `sem_accepted_cumulative.jsonl`，全部判定 append 进 judged_ledger。
   d. ③-D `run_preview(vault, sem=cumulative, hpr=③-B candidates, out_root=S/relations_increment/views)`。
   e. apply：`check_apply_gates` 不过 → notify + 打印原因 + **exit 1**（vault 不动、ledger 不动）；过闸 → 把 out_root 三件**整体替换** `vault/1_extracted/relations/`（canonical、_index_by_policy.json、_index_by_policy/ 目录全删后拷入），然后 ledger.covered += new_pids。
   f. `--dry-run`：a–d 照跑（**含真 judge，会花钱，文档里写明**），跳过 e；打印计数概要。
   g. stdout 一行 json：`{"new_pids":N,"judged":N,"accepted":N,"canonical_edges":N,"applied":bool}`。失败路径 exit 非 0（cron 行靠 `|| notify` 接）。
   注意：**produce_and_push 不在本编排器内**——push 由 cron 行下一段做（与 09:30 L2 行同构）。

测试（`tests/service/test_relations_increment.py`，全部假 judge client / tmp vault fixture，不许真调 LLM）：
1. select_new_pids：增量差集 + 空增量。
2. filter_increment_candidates：涉新过滤 + judged 去重。
3. init-ledger：tmp git repo（subprocess git init/add/commit）→ as-of 提交抽 pid 正确。
4. run 端到端（小 fixture vault，2 旧 1 新政策，假 judge 全 accept）：cumulative 增长、judged_ledger 追加、vault relations 被替换、ledger 更新。
5. 塌缩闸：构造新 canonical 边数 < 旧×0.8 → exit 1、vault 原样、ledger 原样。
6. dry-run：vault 与 ledger 不动。
7. 空增量：直接退出，不跑 judge。

## Task 3 · runbook 追加 02:00 夜间增量行（只改文档）

`docs/runbooks/s2-vps-cron.md` §1 追加（照既有行风格）：
```cron
# 02:00 ③关系增量(容器 LLM judge;增量=新pid×存量;produce_and_push 白名单只放 relations)
0 2 * * * ( /usr/bin/flock -w 7200 9 || { set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.notify "[S2] producer 锁等待超时(7200s),本轮跳过"; exit 1; }; set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.service.relations_increment run --vault /vault --state-dir /state --judge-model deepseek-v4-flash --judge-provider openai && /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault --whitelist 1_extracted/relations/ --message "l2(relations): nightly increment" || /usr/bin/python3 -m scripts.service.notify "[S2] 02:00 关系增量失败,查 relations.log" ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/relations.log 2>&1
```
§4 追加一条：relations 三状态文件说明（pid_ledger / sem_accepted_cumulative / judged_ledger）+ 全量重判兜底 = 手动清 ledger 三件再跑（昂贵,1019 对量级,人工决策）。

## 验收 & 回报

1. 全量 `python3 -m pytest` 全绿（576+新增），输出贴报告。
2. `git log --oneline main..HEAD`（红绿分 commit 可见）+ `git diff main --stat`。
3. 报告落 `docs/handoffs/2026-06-11-codex-wp2a-report.md`：TDD 证据、字段名核对结论（candidates 行的 from/to/candidate_id 实际键名）、偏差。
4. **停在分支等审计。**
