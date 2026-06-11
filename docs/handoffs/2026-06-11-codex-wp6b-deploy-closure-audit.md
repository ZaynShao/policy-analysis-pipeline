# Codex 交接：WP-6b 闭环巡检部署（服务器侧，小包）

**前置**：WP-6a 已审计合 main（`74ff6d7`）。本包：部署（host 模块，无需重建镜像）→ 监督跑 → 装 10:45 cron。
**服务器**：`ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`。

**纪律（红线）**：凭据值不打印不进 git；巡检为只读（不碰 vault 不写 state）；别碰 safety-platform / platform-* / tyo-prod / Mac wewe；任何验证不过停下原样报告。

## Step 0 · 部署

```bash
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main   # 期望 HEAD=74ff6d7
```

## Step 1 · 监督跑（先 --dry-run）

```bash
cd /root/policy-pipeline-src
/usr/bin/python3 -m scripts.service.closure_audit --vault /root/policy-vault --state-dir /root/policy-pipeline-state --dry-run; echo "EXIT=$?"
```

预期两种合法结果：
- 全绿：`{"ok": true, ...}` EXIT=0；
- 有违规：逐项核对——**已知可能的假阳性**：近 20 个 commit 含 6/9-6/10 迁移期非 `policy-pipeline-vps` 作者的历史 commit。若违规项全部为 6/11 之前的历史 commit（`git log` 核日期确认）→ 这是已知窗口效应，**停下报告**（修复方案由 Claude 定：加日期截断），不装 cron；若违规项是 state 活性类 → 停下报告（真实异常）。

全绿才继续 Step 2。再真跑一次（无 --dry-run）确认健康路径静默（无 notify 发出、EXIT=0）。

## Step 2 · 装 10:45 cron

runbook §1 原样复制 10:45 行。核验：`crontab -l | grep -c closure_audit` == 1。

## 回报

逐 Step 输出。重点：Step 1 dry-run 完整输出原文。报告落 `docs/handoffs/2026-06-11-codex-wp6b-report.md`（commit 仅点名该文件，不 push）。
