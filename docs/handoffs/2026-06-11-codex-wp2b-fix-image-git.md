# Codex 交接：WP-2b-fix 容器镜像补 git（本地代码侧，小包）

**背景**：WP-2b 报告（`docs/handoffs/2026-06-11-codex-wp2b-report.md`）：`policy-producer` 用 `policy-pipeline:latest` 镜像，基镜像 `python:3.12-slim` 无 `git`；`relations_increment` → `analysis_high_precision_relations/run.py` 在容器内调 `git ls-files` 报 `FileNotFoundError: 'git'`。本包只修镜像运行时依赖。

**纪律（红线，违者中止）**：本包只许改 `Dockerfile` 一个文件；仓库内既有未跟踪文件（docs/、scripts/service/fetch_proxy_health.py 等）一律不碰不提交；不碰 vault；凭据值不打印不进 git。

## Step 1 · 分支

在 `/Users/shaoziyuan/dev/政策分析-pipeline`（当前 main `15f5319`）建分支 `wp2b/image-git`。

## Step 2 · Dockerfile 加 git

在 `FROM python:3.12-slim` 之后、`WORKDIR /app` 之前插入一层：

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
```

（放在 COPY 之前，利于层缓存。）

## Step 3 · 本地验证（Docker 可用才做）

```bash
docker build -t policy-pipeline:wp2bfix . && docker run --rm policy-pipeline:wp2bfix git --version
```

本机 Docker 不可用/未启动则注明"本地构建跳过，服务器侧 Step 0 重建时验证"，不算失败。

## Step 4 · 提交

单文件 commit（只含 Dockerfile），message 形如 `fix(docker): add git to runtime image for in-container vault reads`。**不要合 main、不要 push**——Claude 审计后合并。

## 回报

stdout 回报：分支名、commit hash、diff 全文、本地验证结果（或跳过原因）。无需 report 文件。
