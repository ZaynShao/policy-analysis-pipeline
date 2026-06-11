# Codex 交接：WP-6c-resume4 前送重跑收尾（服务器侧，小包）

**前置**：确定性 id 修复已审计合 main（`db10dc2`）。cron 两行已在位（容器形态），无需再动 cron。红线同前（凭据值盲、不碰 vault、不打印 PG 数据行内容）。

## 步骤

1. `cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main`（期望 `db10dc2`）。
2. 容器重跑 forward：`docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.l1_review_consumer.sync_l1_pool`。期望 synced 15/15（或 15−既存）；仍有 skip → 停下报告。
3. 只读核验（只打印计数，不打印行内容）：容器内 `select count(*) from "L1ReviewQueue"` 与 `... where verdict is null` 两个数。
4. 容器重跑 reverse 一次：期望无裁决 no-op exit 0。

## 回报

追加到 `docs/handoffs/2026-06-11-codex-wp6c-report.md`（"## 续跑 4"节），commit 仅点名该文件，不 push。
