# Codex 交接：WP-1a 死信告警 + 死信 sweep（代码部分，本地 TDD，不碰服务器）

**背景**：S2 单生产者三线已云上全自动（07:30 评论 / 09:00 L1 / 09:30 L2 归属 / 10:00 投影）。但 run_l2 失败静默：`drain_queue` 失败项落死信 `l2_failures.jsonl`（`scripts/service/orchestrate.py` `_record_failure`，记录格式 `{"pid","error","ts"}`，文件在队列同目录），**没有任何告警，也没有重排机制**。本包补两件：死信增长→飞书告警；死信周度 sweep 回队。这是 WP-1（地基修复）的代码部分；部署与 424 backfill 是 WP-1b，**本包不碰服务器、不动 cron、不合 main、不 push**。

**纪律（红线，违者中止）**：
- 工作仓 = 主 checkout `/Users/shaoziyuan/dev/政策分析-pipeline`（branch main）。**别在 `.claude/worktrees/` 里干活**。
- 从 main 切分支 `wp1/deadletter-alert-sweep`，所有 commit 落该分支。
- 主 checkout 有别条线的未跟踪文件（`docs/2026-06-09-*`、`docs/runbooks/fetch-proxy-*`、`scripts/service/fetch_proxy_health.py`、`docs/superpowers/*2026-06-09*` 等）——**绝不 add/commit/改动**。git add 永远只点名自己的文件。
- 凭据不打印不进 git。本包不需要任何凭据。
- TDD：先红后绿，红绿过程留在 commit 历史里。
- 完成后**停**：不合 main、不 push，写报告等审计。

## Task 1 · `scripts/service/deadletter_alert.py`（死信增长→notify）

设计约束：
- **纯 stdlib**（将来在 VPS host python 跑，同 `produce_and_push`/`notify` 先例，无第三方依赖）。
- 纯函数核心 + CLI 壳（仓内既有风格，参照 `scripts/service/produce_and_push.py`）。

纯函数：
```python
def check_growth(dead_path: Path, state_path: Path) -> str | None:
    """对比死信行数与上次记录。增长→返回告警消息并更新 state；否则返回 None（也要更新 state）。
    dead 文件不存在视为 0 行。state 是 json：{"last_count": int, "checked_at": iso}。
    缩水（rotate 后）→ 不告警，state 跟新值。绝不 raise。"""
```
告警消息含：旧值→新值、最新 1-2 条死信的 pid + error 截断（error 已限 300 字符）。

CLI：
```
python3 -m scripts.service.deadletter_alert --state-dir <DIR>
```
- 死信 = `<DIR>/l2_failures.jsonl`，state = `<DIR>/deadletter_alert_state.json`。
- 有消息 → `scripts.service.notify.send_text(msg)`（绝不 raise 的既有函数）；无论如何 **exit 0**（cron 友好）。
- stdout 打一行 json 概要：`{"dead_count": N, "grew": bool, "notified": bool}`。

测试（`tests/service/test_deadletter_alert.py`，tmp_path）：
1. 死信从 0→2：返回消息含 "0→2" 和最新 pid；state 写入 2。
2. 行数不变：返回 None，state 更新 checked_at。
3. 死信文件不存在：返回 None，state last_count=0。
4. 缩水（5→1，rotate 场景）：不告警，state=1。
5. CLI：send_text 用 monkeypatch 假 adapter/假函数验证调用与 exit 0（不要真发）。

## Task 2 · `scripts/service/deadletter_sweep.py`（死信回队，带放弃上限）

纯函数：
```python
def plan_sweep(dead_records: list[dict], history: dict[str, int],
               max_retries: int = 2, cap: int = 50) -> tuple[list[str], list[str], dict]:
    """死信记录 → (requeue_pids, givenup_pids, new_history)。
    pid 去重保序；history[pid] >= max_retries 的进 givenup（不再回队）；
    requeue 数量 cap 截断（超出部分留在死信文件里等下轮，不丢）；
    new_history = history + requeue 各 pid 计数 +1。"""
```

CLI：
```
python3 -m scripts.service.deadletter_sweep --state-dir <DIR> [--max-retries 2] [--cap 50]
```
流程：
1. 读 `<DIR>/l2_failures.jsonl`；不存在或空 → no-op，stdout `{"swept":0}`，exit 0。
2. 读 `<DIR>/l2_sweep_history.json`（无则 `{}`）。
3. `plan_sweep(...)` → requeue 走既有 `scripts.service.l2_queue.enqueue_batch(queue_path, pids, trigger="sweep", priority="normal", requested_at=<utc iso>)`（queue = `<DIR>/l2_queue.jsonl`；enqueue 自带按 pid 去重）。先确认 `QueueItem.trigger` 无枚举校验（dataclass 注释列了 manual|cron|l1_incremental，确认是自由字符串后用 "sweep"；若有校验则停下报告）。
4. **rotate**：被本轮处理掉的记录（requeue + givenup 的 pid 对应行）append 到 `<DIR>/l2_failures.archived.jsonl`，剩余行（cap 截断留下的）写回 `l2_failures.jsonl`。
5. 写回 history。givenup 非空 → `notify.send_text("[S2] 死信放弃重试 N 条: pid1,pid2,…")`。
6. stdout json 概要：`{"swept":N,"requeued":N,"givenup":N,"left":N}`；恒 exit 0。

测试（`tests/service/test_deadletter_sweep.py`）：
1. 3 条死信（含 1 个重复 pid）→ requeue 2、queue 文件出现 2 条 trigger="sweep"、死信被 rotate、history +1。
2. history 已达 max_retries 的 pid → 进 givenup，不入队。
3. cap=1 截断：1 条入队，其余留在 l2_failures.jsonl。
4. 空/缺文件 no-op。
5. givenup 触发 notify（假函数验证，不真发）。

## Task 3 · runbook 更新（只改文档，不装 cron）

`docs/runbooks/s2-vps-cron.md` §1 crontab 块**追加两行**（照既有行风格，CST）：
```cron
# 09:55 死信增长告警(host python,只读死信+自身state,不需 flock)
55 9 * * * set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.deadletter_alert --state-dir /root/policy-pipeline-state >> /var/log/policy-pipeline/deadletter.log 2>&1

# 周日 08:30 死信 sweep 回队(写队列,必须持 producer flock;回队项当日 09:30 L2 顺手消化)
30 8 * * 0 ( /usr/bin/flock -w 7200 9 || exit 1; set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.deadletter_sweep --state-dir /root/policy-pipeline-state ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/deadletter.log 2>&1
```
并在 §4 已知边界追加一条：sweep 历史 `l2_sweep_history.json`、归档 `l2_failures.archived.jsonl`（放弃项永留归档，人工查）。

## 验收 & 回报

1. 全量测试：`python3 -m pytest` 全绿（含既有 566+），输出贴报告。
2. `git log --oneline main..HEAD` 与 `git diff main --stat` 贴报告。
3. 报告落 `docs/handoffs/2026-06-11-codex-wp1a-report.md`（不含凭据），含：TDD 红绿证据、偏差说明、上面两条 cron 行的最终版本。
4. **停在分支上等审计**，不合 main、不 push。
