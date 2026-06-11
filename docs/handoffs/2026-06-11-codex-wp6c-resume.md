# Codex 交接：WP-6c-resume review_consumer 服务器接线（服务器侧，小包）

**前置**：runbook 两行已审计合 main（`b131883`）。红线同原 handoff `2026-06-11-codex-wp6c-review-consumer-cron.md`（凭据值盲、不碰 vault、只读 pool/写 sink/PG 队列表）。

## 步骤

1. `cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main`（期望 `b131883`）。
2. 手跑两模块各一次（source pipeline.env+notify.env，env 值不打印）：期望优雅 no-op（池空/无裁决），记录 stdout 与 exit code；任一异常 → 停下报告。
3. 装 runbook §1 两行 cron。核验：`crontab -l | grep -c l1_review_consumer` == 2。
4. 顺手记录当前 crontab 总条数（应为 15：12+巡检 1 已在+本包 2）。

## 回报

报告落 `docs/handoffs/2026-06-11-codex-wp6c-report.md`（commit 仅点名该文件，不 push）。
