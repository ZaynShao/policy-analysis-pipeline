# Codex 交接：WP-6c-resume5 重建镜像 + 前送收尾（服务器侧，小包）

**前置**：resume4 仍 0/15 的根因=容器跑镜像代码（旧层），id 修复只在 checkout。本包重建镜像（首用 WP-6d 新 Dockerfile：依赖层吃缓存，只重跑 COPY scripts+`--no-deps -e .`，应数十秒级）。红线同前。

## 步骤

1. `cd /root/policy-pipeline-src`（HEAD 应已是 `db10dc2`，复核一行）。
2. `docker compose -f docker-compose.server.yml build policy-pipeline`。**预期不发生依赖解析**（日志不应出现去 PyPI 解析 anthropic/httpx 的行；若发生且网络超时，等 60s 重试至多 3 次）。
3. 镜像闸：`docker run --rm policy-pipeline:latest python -c "import inspect, scripts.l1_review_consumer.sync_l1_pool as m; assert 'hashlib' in inspect.getsource(m); print('IMAGE_FIX_OK')"`。
4. 容器重跑 forward：期望 synced 15/15、skip 0；仍 skip → 停下报告原始错误。
5. 只读计数核验（只打印两个 count 数字）。
6. 容器重跑 reverse 一次：期望 no-op exit 0。

## 回报

追加到 `docs/handoffs/2026-06-11-codex-wp6c-report.md`（"## 续跑 5"节），commit 仅点名该文件，不 push。
