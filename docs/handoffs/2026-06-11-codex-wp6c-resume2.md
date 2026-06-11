# Codex 交接：WP-6c-resume2 装 psycopg2 + 续跑（服务器侧，小包）

**前置**：resume 停在 host `/usr/bin/python3` 缺 `psycopg2`。Claude 已核实路径疑点：compose 把 `/root/policy-pipeline-src/state` 挂容器 `/app/state`，容器写的 pool 与 host cron 读的是同一路径，接线语义正确。红线同前。

## 步骤

1. `apt-get update && apt-get install -y python3-psycopg2`（Debian 官方包，不动 pip/系统其余）。验证：`/usr/bin/python3 -c "import psycopg2; print(psycopg2.__version__)"`。
2. 按 `2026-06-11-codex-wp6c-resume.md` 步骤 2-4 续跑：手跑两模块（期望优雅 no-op，env 值盲）→ 装两行 cron → 核验 `grep -c l1_review_consumer` == 2 + crontab 总数。

## 回报

**追加**到 `docs/handoffs/2026-06-11-codex-wp6c-report.md`（"## 续跑 2"节），commit 仅点名该文件，不 push。
