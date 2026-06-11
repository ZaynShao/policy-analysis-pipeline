# WP-1b 部署死信告警/sweep + 424 归属 backfill 报告

日期：2026-06-11  
执行机：阿里云东京 `root@8.216.59.173`  
执行边界：未触碰 `/root/safety-platform`、`platform-*` 容器、tyo-prod、Mac wewe-rss 容器；未打印凭据值；vault 写入均经 `produce_and_push`。

## Step 0 服务器部署

命令：

```bash
cd /root/policy-pipeline-src
git fetch --depth=1 origin main
git reset --hard origin/main
python3 -c "from scripts.service.deadletter_alert import check_growth; from scripts.service.deadletter_sweep import plan_sweep; print('modules ok')"
```

关键输出：

```text
HEAD is now at bb52a6c docs: add WP-1a deadletter handoff report
modules ok
bb52a6c
```

结论：部署到 `origin/main` 的 `bb52a6c`，host python 模块导入闸通过；无镜像重建。

## Step 1 安装 cron

命令：从 `docs/runbooks/s2-vps-cron.md` 复制 09:55 死信告警行和周日 08:30 sweep 行进 root crontab，其余行未改。

核验输出：

```text
55 9 * * * set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.deadletter_alert --state-dir /root/policy-pipeline-state >> /var/log/policy-pipeline/deadletter.log 2>&1
30 8 * * 0 ( /usr/bin/flock -w 7200 9 || exit 1; set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.deadletter_sweep --state-dir /root/policy-pipeline-state ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/deadletter.log 2>&1
deadletter_count=2
```

结论：deadletter cron 数量为 2。

## Step 2 投毒验证告警

投毒前状态：

```text
no existing deadletter
```

命令：

```bash
cd /root/policy-pipeline-src
echo '{"pid":"P_TEST_POISON","error":"poison test","ts":"2026-06-11T00:00:00+00:00"}' >> /root/policy-pipeline-state/l2_failures.jsonl
set -a; . /etc/policy-pipeline/notify.env; set +a
/usr/bin/python3 -m scripts.service.deadletter_alert --state-dir /root/policy-pipeline-state
```

关键输出：

```json
{"dead_count": 1, "grew": true, "notified": true}
```

飞书验收：Claude 审计代理确认 `notified:true` 已证明告警代码正确调用发送链路，且该飞书通道在 2026-06-10 W0W1 已端到端验证；用户侧确认转为异步，不阻塞 Step 3。

清理命令：

```bash
rm /root/policy-pipeline-state/l2_failures.jsonl
/usr/bin/python3 -m scripts.service.deadletter_alert --state-dir /root/policy-pipeline-state
```

清理输出：

```json
{"dead_count": 0, "grew": false, "notified": false}
```

```text
deadletter file removed
```

## Step 3.1 生成无 business_view 清单

命令：按 handoff Python 片段只读扫描 `/root/policy-vault/0_raw/policies`，输出到 `/root/policy-pipeline-state/backfill_20260611.txt`。

关键输出：

```text
missing business_view: 428
427 /root/policy-pipeline-state/backfill_20260611.txt
```

说明：`wc -l` 为 427 是因为文件末尾无换行；Python 计数和后续读取确认实际清单为 428 条，落在 424±30 范围内。

## Step 3.2 分块入队 + drain

每批均使用：

```bash
cd /root/policy-pipeline-src
flock /var/lock/policy-pipeline-producer.lock bash -c '... enqueue_batch ... run_l2 ... produce_and_push ...'
```

模型参数：

```text
--gen-model deepseek-v4-flash --gen-provider openai
--judge-model deepseek-v4-flash --judge-provider openai
```

同模型 judge 警告多次出现，属于预期 warning，非阻断条件：

```text
[warn] gen 与 judge 同模型(deepseek-v4-flash):judge 独立性退化为自评，质量打折
```

批次结果：

| batch | start CST | size | processed | ok | failed | skipped | pushed paths | queue after | deadletter after | bv_total | remaining |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | 12:10 | 100 | 98 | 98 | 0 | 0 | 83 | 0 | no deadletter | 884 | 328 |
| 2 | 13:10 | 100 | 100 | 100 | 0 | 1 | 90 | 0 | no deadletter | 974 | 228 |
| 3 | 13:53 | 100 | 99 | 99 | 0 | 0 | 98 | 0 | no deadletter | 1072 | 128 |
| 4 | 14:21 | 100 | 96 | 96 | 0 | 1 | 93 | 0 | no deadletter | 1165 | 28 |
| 5 | 14:56 | 28 | 28 | 28 | 0 | 0 | 27 | 0 | no deadletter | 1192 | 0 |

首块监督门：

```json
{"processed": 98, "ok": 98, "failed": 0, "skipped": 0}
```

结论：首块 `failed/processed = 0%`，未触发 >10% 停止条件。

总计：

```text
processed=421 ok=421 failed=0 skipped=2
l2_queue.jsonl final lines=0
l2_failures.jsonl final=no deadletter
backfill_20260611.txt remaining=0
business_view_total=1192
```

时窗：所有批次均在 2026-06-11 12:10-15:04 CST 执行，未跨入次日 07:00-10:30 CST 产线窗口。

## Step 3.3 收尾投影 + 总验收

命令：

```bash
cd /root/policy-pipeline-src
flock /var/lock/policy-pipeline-producer.lock docker compose -f docker-compose.server.yml run --rm \
  policy-pipeline python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1
head -c 400 /root/policy-pipeline-state/last_sync_run.json; echo
```

关键输出：

```json
{"synced_count": 1176, "skipped_override_count": 0, "relation_count": 1123, "errors": [], "skipped_invalid_count": 15, "commentary_count": 171}
```

验收：

```text
synced_count=1176
errors=[]
relation_count=1123
skipped_invalid_count=15
```

偏差说明：

- `synced_count=1176`，在 1200±30 预期范围内。
- `relation_count=1123`，大于 WP-2 基线 992，恢复 `1123 - 992 = 131` 条关系。
- 最终无死信文件，无死信样例。

vault 核验：

```text
git -C /root/policy-vault -c core.quotepath=false status --short
# empty
vault_head=9dd43e2d1f50eb55e7106c60c6b0a68473ea7f6a
vault_origin_main=9dd43e2d1f50eb55e7106c60c6b0a68473ea7f6a
vault_head_matches_origin_main=yes
```

source 核验：

```text
cd /root/policy-pipeline-src
git rev-parse --short HEAD
bb52a6c
git status --short
?? scripts/__pycache__/
?? scripts/l1_collect/__pycache__/
?? scripts/l1_collect/commentary_ingest/__pycache__/
?? scripts/l1_collect/commentary_ingest/qr_relay/__pycache__/
?? scripts/service/__pycache__/
```

说明：`/root/policy-pipeline-src` 仍有运行 Python 生成的未跟踪 `__pycache__` 目录；本次未纳入任何 git 操作。业务验收以 vault clean、queue/deadletter clean、projection clean 为准。

## 结论

WP-1b 服务器侧完成：

- deadletter alert/sweep 已部署并安装 cron。
- 投毒告警链路返回 `notified:true`，测试死信已清理并归零。
- 428 条缺 business_view 清单已分 5 批 drain，首块监督门通过，全批次 `failed=0`。
- final sync 投影 `errors=[]`，`synced_count=1176`，`relation_count=1123`。
- vault 干净且 HEAD 等于 `origin/main`。

后续建议：WP-2 可使用 `relation_count=1123` 作为新基线；若后续 09:55 deadletter cron 告警出现，应按真实新增死信处理。
