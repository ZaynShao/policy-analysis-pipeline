# Codex 交接：WP-6c-resume3 容器形态接线（服务器侧，小包）

**前置**：heng-pg 仅在 platform-net 容器网络可解析，runbook 两行已改为 `docker compose run --rm policy-producer` 形态并合 main（`397b719`）。红线同前（凭据值盲、不碰 vault）。

## 步骤

1. `cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main`（期望 `397b719`）。
2. 手跑两模块各一次（照 runbook 新行，容器内 env_file 自带 DATABASE_URL）：期望连上 PG 且优雅 no-op（pool 空/无裁决），记录 stdout+exit code；连接失败或异常 → 停下报告。
3. 装 runbook §1 两行 cron（容器形态）。核验 `crontab -l | grep -c l1_review_consumer` == 2。
4. 记录 crontab 总条数。

## 回报

追加到 `docs/handoffs/2026-06-11-codex-wp6c-report.md`（"## 续跑 3"节），commit 仅点名该文件，不 push。
