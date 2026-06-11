# WP-2a ③关系族增量编排器代码交接

日期:2026-06-11  
分支:`wp2/relations-increment`  
范围:本地 TDD 代码部分;不碰服务器、不动 cron 实机、不合 main、不 push。

## 当前进程

当前处在 WP-2a:③关系层增量编排器代码与 runbook 接线文本。WP-2b 才是服务器部署、种子初始化和补课跑批。

本步完成:
- `state/node3c/sem_accepted_20260606_seed.jsonl` 入 git lineage,537 行。
- 新增 `scripts/service/relations_increment.py`。
- 新增 `tests/service/test_relations_increment.py`。
- `docs/runbooks/s2-vps-cron.md` 追加 02:00 关系增量 cron 文本和三状态文件说明。

原则/门禁:
- 未触碰服务器、cron 实机、main、远端 push。
- 不在 `scripts/l2_themescore/` 引入真实政策 PID;principle guard 通过。
- ③-D 仍走确定性全量 preview,本编排器只做增量判定和 relations 整体替换。
- apply 前有 preview 三件完整性、canonical 非空、旧边数保留比例安全闸。

## TDD 证据

RED:

```bash
python3 -m pytest tests/service/test_relations_increment.py
```

结果:采集阶段失败,原因是 `scripts.service.relations_increment` 尚不存在。

GREEN:

```bash
python3 -m pytest tests/service/test_relations_increment.py
```

结果:`7 passed in 0.94s`。

关系层相关回归:

```bash
python3 -m pytest tests/service/test_relations_increment.py tests/analysis_semantic_relations tests/analysis_relation_views tests/analysis_high_precision_relations
```

结果:`64 passed in 1.36s`。

全量验证:

```bash
python3 -m pytest
```

结果:`583 passed, 1 warning in 6.17s`。warning 为本机 urllib3/LibreSSL 环境警告,非本次代码新增失败。

红线 guard:

```bash
python3 -m scripts.audit.principle_guard scripts/l2_themescore
```

结果:exit 0。

## 字段名核对

③-C `SemanticCandidate.to_row()` 实际候选行键:
- `candidate_id`
- `schema_version`
- `from`
- `to`
- `rel`
- `symmetric`
- `candidate_basis`
- `evidence`
- `source`

③-B `high_precision_relation_candidates.jsonl` 实际候选行键:
- `candidate_id`
- `schema_version`
- `from`
- `to`
- `rel`
- `doc_number`
- `evidence`
- `location`
- `confidence`
- `from_path`
- `to_path`
- `rules`
- `extracted_by`

本编排器的增量过滤使用实际键名 `from` / `to` / `candidate_id`。

## 行为说明

状态文件在 `--state-dir`:
- `relations_pid_ledger.json`:已覆盖 pid 集,只有空增量和 dry-run 不更新。
- `sem_accepted_cumulative.jsonl`:累积 accepted;部署时应由 537 行 seed 初始化。
- `relations_judged_ledger.jsonl`:append-only 判定账本,防重判。

`run` 流程:
1. 运行 ③-B 全量 preview 到 `state_dir/relations_increment/hpr`。
2. 用与 ③-B 同口径的 git tracked policy files 取当前 pid。
3. 对 tracked - covered 保序取新 pid;空增量直接返回 `{"new_pids":0}`。
4. ③-C 全量免费生成候选,仅保留触及新 pid 且未 judged 的候选。
5. program gate 后逐条 judge,accepted 追加到 cumulative,全部判定追加 judged ledger。
6. 调 ③-D `run_preview` 用 cumulative + HPR 全量重生 views。
7. 非 dry-run 时过 apply gates 后整体替换 `vault/1_extracted/relations/`,再更新 pid ledger。

`--dry-run` 按交接要求执行 a-d,含真实 judge,会写 semantic cumulative / judged ledger;只跳过 vault apply 和 pid ledger 更新。

## 偏差与注意

- `state/node3c` 被 `.gitignore` 覆盖;按用户明确要求,只对 `state/node3c/sem_accepted_20260606_seed.jsonl` 使用 `git add -f`。
- 本地全量测试数为 583,不是交接文本里的 576+;新增 7 个 relations increment 测试已包含在内。
- 未执行真实 LLM;测试均用假 judge client。CLI 正式运行若不传注入 client,会按 `--judge-provider openai` 构造 `OpenAICompatClient`。
- 未做服务器初始化。WP-2b 部署前需要把 `sem_accepted_cumulative.jsonl` 用 seed 初始化,并用 `init-ledger --as-of-commit <2026-06-06全量冻结对应vault commit>` 建 pid ledger。

## 下一步建议

推荐 WP-2b 先做受监督 dry-run:初始化三状态文件后,在服务器容器内跑一次 `relations_increment run --dry-run`,确认 `new_pids`、`judged`、`accepted`、`canonical_edges` 与预期一致,再解开 02:00 cron。
