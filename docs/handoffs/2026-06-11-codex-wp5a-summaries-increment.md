# Codex 交接：WP-5a policy_summaries 增量生产者（本地代码侧）

**背景**：SCHEMA §5.1 契约在、生产者缺位（scripts/l2_derive 已空）。vault `1_extracted/policy_summaries.jsonl` 现有 934 行建设期产物：696 行 policy_id 直配当前 pid，238 行为 pre-②-A 旧 id（部分可经 raw frontmatter `aliases` 恢复）。本包新建增量生产者，**模式照抄 `scripts/service/relations_increment.py`**（pid ledger / dry-run 落缓存不重花钱 / 程序闸 / SystemExit+notify）。

**契约（SCHEMA §5.1，逐字段）**：每行 `{"policy_id", "summary"(2-3 句客观摘要：范围/对象/截止日/数量目标), "summary_one_liner"(≤25 字), "reading_value"(≤25 字), "extracted_at"(iso), "extracted_by"("scripts/service/summaries_increment.py"), "extracted_model"}`（extracted_model 为新增可选字段，记录生成模型）。

**纪律（红线，违者中止）**：TDD 红绿分 commit；只许新建 `scripts/service/summaries_increment.py` + `tests/service/test_summaries_increment.py` + `scripts/service/summaries_nightly.sh` + runbook 04:00 行；既有未跟踪文件不碰；不合 main 不 push；不碰 vault；凭据值盲。LLM client 用现成 `scripts.common.llm.OpenAICompatClient`（带 log_path），不新写 client。

**分支**：`wp5/summaries-increment`（从 main `cada9a7` 起）。

## 模块 CLI（镜像 relations_increment 语义）

### `init-ledger --vault V --state-dir S [--apply]`
1. 读 vault `1_extracted/policy_summaries.jsonl` 全部行 + raw frontmatter（id/aliases）建映射；
2. 直配行保留；旧 id 经 aliases 可映射到当前 pid 的行**重写 policy_id** 保留（原 id 记入行内新字段 `normalized_from`）；不可恢复行剔除并写 `S/summaries_quarantine.jsonl`（含剔除原因）；同 pid 多行保留 extracted_at 最新一行；
3. 无 `--apply`：只打印报告 JSON（kept_direct/kept_alias/quarantined/dedup_dropped/covered 总数），不写任何文件；
4. `--apply`：规范化文件写回 vault 路径（整文件重写）+ ledger `S/summaries_pid_ledger.json`（`{"covered":[...],"updated_at"}` 格式同 relations 的 write_pid_ledger）。**vault push 不在本模块内**（由调用方 produce_and_push）。

### `run --vault V --state-dir S --model M --provider openai [--dry-run] [--limit N]`
1. `new = tracked 当前唯一 pid − ledger.covered`（tracked 口径同 relations_increment 的 `_tracked_policy_pids`，dup-pid 文件取 id 首见）；
2. 逐 pid：输入 = raw frontmatter(title/issuer/date) + 正文前 3000 字符 → LLM 生成三字段（prompt 内嵌契约说明，输出 JSON，schema 校验）；
3. **程序闸**：one_liner/reading_value ≤25 字（len 按字符）、summary 非空且 ≤400 字符、三字段均非空。不过闸→重试 1 次→仍不过进 `S/summaries_review_queue.jsonl`，不阻塞其余 pid；
4. 生成行先落 `S/summaries_staging.jsonl`（**含 dry-run，缓存防重花**；已在 staging 的 pid 不再调 LLM）；
5. `--dry-run`：打印 summary JSON（new/generated/queued/staged 计数）后结束，不写 vault；
6. 真跑：staging 中所有不在 vault 文件内的 pid 行 **append** 到 vault `1_extracted/policy_summaries.jsonl`；apply 闸：append 后文件无重复 policy_id 且行数=原行数+新增数，违反→notify+SystemExit(1) 不写；成功后 ledger covered += 这批 pid，staging 清空已应用行；
7. `--limit N`：本轮最多处理 N 个新 pid（回填分批用）。

## `scripts/service/summaries_nightly.sh` + runbook

模式照抄 signals_nightly.sh（同锁、notify.env、失败 notify "[S2] 04:00 摘要增量失败,查 summaries.log"）：容器跑 `run --vault /vault --state-dir /state --model deepseek-v4-flash --provider openai` → host `produce_and_push --whitelist 1_extracted/policy_summaries.jsonl --message "l2(summaries): nightly increment"`。runbook §1 加 04:00 短行 `>> /var/log/policy-pipeline/summaries.log`。

## 测试要求（红 commit 先行）

init-ledger：直配/alias 恢复/quarantine/同 pid 去重/--apply 写盘与否。run：增量选集、程序闸（超长截/空值进 queue）、staging 缓存防重调（mock client 计数）、apply 闸（重复 pid 拒绝）、dry-run 不写 vault、--limit。LLM 一律 mock。

## 验证

`python3 -m pytest` 全绿（588 基线+新增）；`bash -n` 脚本。

## 回报

stdout：分支、红绿 commit、pytest 数字、模块行数。无需 report 文件。
