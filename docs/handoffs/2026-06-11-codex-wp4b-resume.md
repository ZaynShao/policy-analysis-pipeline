# Codex 交接：WP-4b-resume 上下文链续跑（服务器侧）

**前置**：WP-4c（analysis_context 兼容 canonical）已审计合 main（`7db6d78`）。WP-4b 首跑已完成 Step 0/1（checkout、03:00 cron 切换、临时脚本清理），本包从 Step 2 续跑。红线同 `2026-06-11-codex-wp4b-deploy-contexts.md`（**全程不得有 vault 写入**，前后各记 vault status/HEAD 必须不变）。

## Step 0' · 更新部署

```bash
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main   # 期望 HEAD=7db6d78
```

**镜像需重建**（本次改了容器内 python：`scripts/analysis_context/run.py`）：

```bash
docker compose -f docker-compose.server.yml build policy-pipeline
# 构建若因 pip 网络超时失败:等 ≥60s 重试,最多 3 次;3 次同因失败停下报告(勿改源/配镜像源)
docker run --rm policy-pipeline:latest python -c "import scripts.analysis_context.run as m; import inspect; assert 'other_rel_counts' in inspect.getsource(m); print('IMAGE_OK')"
```

## Step 2 · 监督跑上下文链（同原 handoff）

`/root/policy-pipeline-src/scripts/service/contexts_nightly.sh; echo "EXIT=$?"`

监督门（任一不过停下报告）：EXIT=0；三个 nightly state 目录产物存在且 mtime 今天；cat 各 summary 关键数（policy/theme/region context 行数、analysis_context 行数及 `rel_vocabulary_seen`——应含 8 种 rel 且总数 ≈1669、inventory 边数与 canonical 1669 同量级）；vault 前后 status 干净、HEAD 不变（`307f8a4a` 或当前值）。

## Step 3 · 装 03:30 cron（同原 handoff）

runbook §1 原样复制 03:30 行。核验 `crontab -l | grep -c contexts_nightly` == 1。

## 回报

**追加**到 `docs/handoffs/2026-06-11-codex-wp4b-report.md`（"## 续跑"一节），commit 仅点名该文件，不 push。
