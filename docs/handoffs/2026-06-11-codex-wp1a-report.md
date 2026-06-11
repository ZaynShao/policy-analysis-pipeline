# WP-1a 死信告警 + 死信 sweep 代码交接

日期: 2026-06-11
分支: `wp1/deadletter-alert-sweep`
范围: 本地代码、测试、runbook 文本。不碰服务器、不装 cron、不 backfill、不合 main、不 push。

## 完成内容

1. 新增 `scripts/service/deadletter_alert.py`
   - `check_growth(dead_path, state_path)` 对比 `l2_failures.jsonl` 行数与 `deadletter_alert_state.json`。
   - 死信不存在按 0 行处理。
   - 增长时返回飞书告警文本,包含旧值到新值和最新 1-2 条 `pid + error`。
   - 不增长或缩水只更新 state,不告警。
   - CLI: `python3 -m scripts.service.deadletter_alert --state-dir <DIR>`; stdout 输出 `{"dead_count":N,"grew":bool,"notified":bool}`;恒 exit 0。

2. 新增 `scripts/service/deadletter_sweep.py`
   - `plan_sweep(dead_records, history, max_retries=2, cap=50)` 输出 `(requeue_pids, givenup_pids, new_history)`。
   - pid 去重保序;达到 `max_retries` 的 pid 进入 givenup;回队数量受 `cap` 限制;history 只对本轮回队 pid +1。
   - CLI: `python3 -m scripts.service.deadletter_sweep --state-dir <DIR> [--max-retries 2] [--cap 50]`;恒 exit 0。
   - 回队写 `<DIR>/l2_queue.jsonl`,使用既有 `l2_queue.enqueue_batch(..., trigger="sweep", priority="normal")`。
   - 已确认 `QueueItem.trigger` 无枚举校验,只是 dataclass 注释,可使用 `"sweep"`。
   - 本轮处理的死信行归档到 `l2_failures.archived.jsonl`;cap 留下的行继续保留在 `l2_failures.jsonl`。
   - givenup 非空时调用 `notify.send_text("[S2] 死信放弃重试 N 条: ...")`。

3. 更新 `docs/runbooks/s2-vps-cron.md`
   - §1 crontab 块追加死信增长告警和周日 sweep 两行。
   - §4 已知边界追加 `l2_sweep_history.json` 与 `l2_failures.archived.jsonl` 说明。

## TDD 证据

红灯:

```text
python3 -m pytest tests/service/test_deadletter_alert.py tests/service/test_deadletter_sweep.py
collected 0 items / 2 errors
ImportError: cannot import name 'deadletter_alert' from 'scripts.service'
ImportError: cannot import name 'deadletter_sweep' from 'scripts.service'
```

绿灯:

```text
python3 -m pytest tests/service/test_deadletter_alert.py tests/service/test_deadletter_sweep.py
collected 10 items
tests/service/test_deadletter_alert.py .....                             [ 50%]
tests/service/test_deadletter_sweep.py .....                             [100%]
10 passed in 0.04s
```

全量验收:

```text
python3 -m pytest
collected 576 items
576 passed, 1 warning in 4.64s
```

唯一 warning 是本机 urllib3/OpenSSL 版本提示,与本包无关:

```text
NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' module is compiled with 'LibreSSL 2.8.3'
```

## git 证据

当前提交:

```text
95c5db8 docs: document deadletter cron hooks
7d0ab6a service: add L2 deadletter alert and sweep
```

写本报告前的 diff stat:

```text
docs/runbooks/s2-vps-cron.md           |   7 ++
scripts/service/deadletter_alert.py    |  99 +++++++++++++++++++++++
scripts/service/deadletter_sweep.py    | 142 +++++++++++++++++++++++++++++++++
tests/service/test_deadletter_alert.py |  88 ++++++++++++++++++++
tests/service/test_deadletter_sweep.py | 116 +++++++++++++++++++++++++++
5 files changed, 452 insertions(+)
```

## 最终 cron 文本

```cron
# 09:55 死信增长告警(host python,只读死信+自身state,不需 flock)
55 9 * * * set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.deadletter_alert --state-dir /root/policy-pipeline-state >> /var/log/policy-pipeline/deadletter.log 2>&1

# 周日 08:30 死信 sweep 回队(写队列,必须持 producer flock;回队项当日 09:30 L2 顺手消化)
30 8 * * 0 ( /usr/bin/flock -w 7200 9 || exit 1; set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.deadletter_sweep --state-dir /root/policy-pipeline-state ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/deadletter.log 2>&1
```

## 偏差说明

- 无功能偏差。
- 未触碰服务器、未安装 crontab、未执行生产命令、未读取或打印凭据。
- 主 checkout 仍有别条线未跟踪文件;本包提交只点名加入 WP-1a 自己的文件。

## 当前状态与下一步

当前仍在 WP-1a 代码包。原则/门禁仍生效:raw 不可变、dry-run/apply 边界不涉及本包、凭据不进 git、生产环境未触碰。

推荐下一步是人工审计本分支 diff。审计通过后再进入 WP-1b:部署 runbook 中两条 cron、观察 deadletter 日志、再处理 424 backfill。
