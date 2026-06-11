# Codex 交接：WP-2b-resume ③增量上云续跑（服务器侧）

**前置**：WP-2b 首跑停在 Step 2（容器缺 git，见 `2026-06-11-codex-wp2b-report.md`）；Dockerfile 修复已合 main。本包按原 handoff `2026-06-11-codex-wp2b-deploy-catchup.md` 的 Step 0→5 续跑，**以下修订优先**：

**纪律（红线）与服务器同原 handoff**：凭据值不打印不进 git；vault 写只经编排器 apply + `produce_and_push`，绝不手工 git add/commit vault；真跑必持 `flock /var/lock/policy-pipeline-producer.lock`；别碰 `/root/safety-platform`、`platform-*`、tyo-prod、Mac wewe 容器；不跨进 07:00–10:30 CST 产线窗口；任何验证不过停下原样报告。

## 修订

1. **Step 0 重建必做**（main 已含 Dockerfile git 修复），镜像闸加一条：
   ```bash
   docker run --rm policy-pipeline:latest git --version   # 必须输出版本号
   docker run --rm policy-pipeline:latest sh -c "grep -c check_apply_gates /app/scripts/service/relations_increment.py"   # ≥1
   ```
2. **Step 1 已完成，只验不做**：
   ```bash
   wc -l /root/policy-pipeline-state/sem_accepted_cumulative.jsonl   # 期望 537
   python3 -c "import json;print(len(json.load(open('/root/policy-pipeline-state/relations_pid_ledger.json'))['covered']))"   # 期望 873
   ```
   两数对上即跳过 Step 1；对不上 → 停下报告。**勿重跑 init-ledger。**
3. Step 2→5 按原 handoff 原样执行（监督门三数、真跑 apply+push、投影验证 relation_count>1123、装 02:00 cron）。

## 回报

报告**追加**到 `docs/handoffs/2026-06-11-codex-wp2b-report.md`（新增"## 续跑（resume）"一节，逐 Step 命令+关键输出，env 值打码），commit 仅点名该文件。
