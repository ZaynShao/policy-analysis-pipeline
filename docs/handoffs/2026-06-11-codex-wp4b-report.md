# WP-4b 服务器部署报告

时间：2026-06-11 16:50 CST 起  
范围：部署 WP-4a main、03:00 cron 切到 repo 脚本、监督跑 03:30 上下文链、按门禁决定是否安装 03:30 cron。

结论：Step 0 和 Step 1 完成；Step 2 未通过，已按红线停止，未安装 03:30 cron。vault 跑前跑后 HEAD/status 完全不变。

## Step 0 · 部署

命令：

```bash
cd /root/policy-pipeline-src
git fetch --depth=1 origin main
git reset --hard origin/main
git rev-parse --short HEAD
test -x scripts/service/signals_nightly.sh && test -x scripts/service/contexts_nightly.sh && echo SCRIPTS_EXEC_OK
```

关键输出：

```text
SERVER_TIME=2026-06-11 16:50:28 CST
HEAD is now at aab069d ops: script nightly signals and contexts
aab069d
SCRIPTS_EXEC_OK
```

说明：服务器时间不在 07:00-10:30 CST 禁跑窗口；无需重建镜像。

## Step 1 · 03:00 cron 切换与临时脚本清理

动作：将 root crontab 的 `0 3 * * *` 行替换为 runbook 短行：

```cron
0 3 * * * /root/policy-pipeline-src/scripts/service/signals_nightly.sh >> /var/log/policy-pipeline/signals.log 2>&1
```

核验与清理输出：

```text
signals_count=1
state_bin_refs=0
ls: cannot access '/root/policy-pipeline-state/bin': No such file or directory
```

说明：旧 `/root/policy-pipeline-state/bin/commentary_signals.run_nightly.sh` 已移除，bin 目录不存在。

## Step 2 · 监督跑上下文链

跑前 vault 证据：

```text
VAULT_HEAD_BEFORE=307f8a4a
VAULT_STATUS_BEFORE_BEGIN
VAULT_STATUS_BEFORE_END
```

执行命令：

```bash
/root/policy-pipeline-src/scripts/service/contexts_nightly.sh
```

结果：失败，脚本退出码为 1；已触发脚本内 notify。

关键输出：

```text
ValueError: relation row missing required field: candidate_id
notify sent=True
```

已完成的 signal context summary：

```json
{
  "accepted_commentary_signals": 186,
  "accepted_market_signals": 6,
  "blocked_signal_count": 38,
  "policy_context_count": 94,
  "theme_context_count": 13,
  "region_context_count": 6,
  "unknown_region_market_signals": 0,
  "region_warning_count": 1,
  "coverage_warnings": {
    "commentary_only": 3,
    "none": 10
  }
}
```

mtime：

```text
2026-06-11 16:50:57.023806026 +0800 /root/policy-pipeline-state/signal_context/nightly/summary.json
```

未生成的必需产物：

```text
stat: cannot stat '/root/policy-pipeline-state/analysis_layer/nightly/summary.json': No such file or directory
stat: cannot stat '/root/policy-pipeline-state/analysis_layer/nightly/analysis_context_summary.json': No such file or directory
find: ‘/root/policy-pipeline-state/analysis_layer/nightly’: No such file or directory
find: ‘/root/policy-pipeline-state/analysis_layer/nightly_inventory’: No such file or directory
```

跑后 vault 证据：

```text
VAULT_HEAD_AFTER=307f8a4a
VAULT_STATUS_AFTER_BEGIN
VAULT_STATUS_AFTER_END
```

vault 结论：跑前跑后 HEAD 均为 `307f8a4a`，`status --short` 均为空，确认本包没有写 vault。

失败定位线索：

```text
contexts_nightly.sh passes:
--relations /vault/1_extracted/relations/relations_canonical.jsonl

analysis_context.run requires:
candidate_id, from, to, rel

relations_canonical.jsonl first row keys:
['confidence', 'evidence', 'from', 'rel', 'source', 'to']

first row rel:
aligns_with
```

说明：当前 canonical relations 行缺少 `candidate_id`，且包含 `analysis_context` 当前支持范围外的 `aligns_with`。这是 Step 2 失败的直接输入契约不匹配。未继续执行 inventory 阶段。

## Step 3 · 03:30 cron

未执行。原因：Step 2 的 `EXIT=0`、analysis summary、inventory 产物门未通过。

核验：

```text
contexts_count=0
```

当前 crontab 结构摘要（不展开 env/参数）：

```text
30 7 * * * -> scripts.service.notify + scripts.service.produce_and_push + scripts.service.notify
0 9 * * * -> scripts.service.notify + scripts.service.produce_and_push + scripts.service.notify
30 9 * * * -> scripts.service.notify + scripts.service.produce_and_push + scripts.service.notify
0 10 * * * -> scripts.service.notify + scripts.service.notify
30 9 * * * -> set
0 */6 * * * -> scripts.service.notify
0 21 * * * -> scripts.service.sync_tick
55 9 * * * -> scripts.service.deadletter_alert
30 8 * * 0 -> scripts.service.deadletter_sweep
0 2 * * * -> scripts.service.notify + scripts.service.produce_and_push + scripts.service.notify
0 3 * * * -> scripts/service/signals_nightly.sh
```

## 当前进程位置与下一步

当前仍在 WP-4b 服务器部署进程内；本步已完成部署和 03:00 脚本收编切换，但 03:30 上下文链因 relation 输入契约不匹配未通过监督门。原则/门禁仍生效：未写 vault、未安装失败链 cron、未跨禁跑窗口。

推荐下一步：先修复 `analysis_context` 与 `relations_canonical.jsonl` 的输入契约。可选路径是让 canonical 产物提供 `candidate_id` 并过滤/映射到 `analysis_context` 支持的关系类型，或让 `analysis_context` 明确兼容 canonical schema 与语义关系范围；修复后重新走 WP-4b Step 2，再安装 03:30 cron。
