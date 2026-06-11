# Codex 交接：WP-2b-resume2 重试镜像构建 + 续跑（服务器侧）

**背景**：resume 首跑 Step 0 build 失败。Claude 判读：`WARNING: Retrying ... ReadTimeoutError ... /simple/httpcore/` 表明 pip 拉不到 httpcore 索引元数据 → 解析器视 httpcore 无候选 → **假性** ResolutionImpossible（anthropic + httpx 0.28.1 + httpcore 1.x 实际可共存，早上缓存层即此组合）。处置=重试，不改 Dockerfile/pyproject、不配镜像源。

**纪律（红线）同 `2026-06-11-codex-wp2b-resume.md`**：凭据值不打印不进 git；vault 写只经编排器 apply + `produce_and_push`；真跑必持 `flock /var/lock/policy-pipeline-producer.lock`；别碰 safety-platform / platform-* / tyo-prod / Mac wewe；不跨进 07:00–10:30 CST 窗口；任何验证不过停下原样报告。

## Step 0' · 重试构建

```bash
cd /root/policy-pipeline-src   # HEAD 应已是 9f78512,无需再 pull
docker compose -f docker-compose.server.yml build policy-pipeline
```

失败于网络超时 → 等 ≥60 秒再试，**最多 3 次**。3 次同因失败 → 停下报告（修复方案由 Claude 定，勿自行改源/配镜像源/换 Dockerfile）。

成功后镜像双闸（都过才往下）：

```bash
docker run --rm policy-pipeline:latest git --version          # 必须输出版本号
docker run --rm policy-pipeline:latest sh -c "grep -c check_apply_gates /app/scripts/service/relations_increment.py"   # ≥1
```

## 之后

按 `2026-06-11-codex-wp2b-resume.md` 修订 2、3 继续：Step 1 只验不做（537 / 873，勿重跑 init-ledger）→ Step 2 监督 dry-run（三数门）→ Step 3 真跑 apply+push → Step 4 投影验证 relation_count>1123 → Step 5 装 02:00 cron。

## 回报

继续追加到 `docs/handoffs/2026-06-11-codex-wp2b-report.md`（"## 续跑 2"一节），commit 仅点名该文件。
