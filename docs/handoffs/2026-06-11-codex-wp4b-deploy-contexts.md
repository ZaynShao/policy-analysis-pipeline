# Codex 交接：WP-4b ④上下文链服务器部署 + 03:00 脚本收编切换（服务器侧）

**前置**：WP-4a 已审计合 main（`aab069d`）。本包：部署 → 03:00 cron 切到 repo 脚本并清理临时脚本 → 监督跑 03:30 上下文链一次 → 装 03:30 cron。
**服务器**：`ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`。

**纪律（红线，违者中止）**：凭据值不打印不进 git；本包**不应有任何 vault 写入**（上下文链只写 /state）——跑链前后各记一次 `git -C /root/policy-vault status --short` 与 HEAD，必须完全不变；手跑链必须直接执行脚本本体（脚本自带 flock）；别碰 safety-platform / platform-* / tyo-prod / Mac wewe；不跨进 07:00–10:30 CST 窗口；任何验证不过停下原样报告。

## Step 0 · 部署

```bash
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main   # 期望 HEAD=aab069d
test -x scripts/service/signals_nightly.sh && test -x scripts/service/contexts_nightly.sh && echo "SCRIPTS_EXEC_OK"
```

无需重建镜像（无 python 改动）。

## Step 1 · 03:00 cron 切换 + 临时脚本清理

把 crontab 里 03:00 行替换为 runbook §1 的短行（指向 `/root/policy-pipeline-src/scripts/service/signals_nightly.sh`），其余行不动。然后：

```bash
crontab -l | grep "signals_nightly.sh" | wc -l    # ==1
crontab -l | grep -c "policy-pipeline-state/bin"  # ==0
rm -f /root/policy-pipeline-state/bin/commentary_signals.run_nightly.sh && rmdir /root/policy-pipeline-state/bin 2>/dev/null; ls /root/policy-pipeline-state/bin 2>&1
```

## Step 2 · 监督跑上下文链

```bash
/root/policy-pipeline-src/scripts/service/contexts_nightly.sh; echo "EXIT=$?"
```

**监督门**（任一不过 → 停下报告）：
- EXIT=0；
- `/root/policy-pipeline-state/signal_context/nightly/summary.json`、`/root/policy-pipeline-state/analysis_layer/nightly/summary.json`（或模块实际 summary 文件名）、`/root/policy-pipeline-state/analysis_layer/nightly_inventory/` 下产物均存在且 mtime 为今天；逐个 cat summary 关键数（policy/theme/region context 行数、analysis_context 行数、inventory 边数——inventory 边数应与 canonical 1669 同量级）；
- vault 前后对比：status 均干净、HEAD 均为跑前值（不变）。

## Step 3 · 装 03:30 cron

从 runbook §1 原样复制 03:30 行。核验：`crontab -l | grep -c contexts_nightly` == 1；当前 crontab 总行结构报告一次（每行时间+脚本/模块名即可，不贴 env）。

## 回报

逐 Step 命令+关键输出。重点：Step 2 各 summary 数字、vault 不变证据、最终 crontab 结构。报告落 `docs/handoffs/2026-06-11-codex-wp4b-report.md`（commit 仅点名该文件，不 push）。
