# Codex 交接：WP-4a ④上下文装配+③-E 夜间链（本地代码侧）

**背景**：三个模块已存在且 preview-only、零 LLM、带测试：`scripts/signal_context/run.py`（读 vault 两个信号文件 → policy/theme/region context）、`scripts/analysis_context/run.py`（`--relations` + `--policy-context` → analysis_context）、`scripts/analysis_relation_inventory/run.py`（③-E 关系资产盘点）。它们是 ④ 的备料层，产物落 /state（SCHEMA 无 vault 契约），**不需要 produce_and_push**。
另：WP-3b 实战发现 crontab 有行长上限，超长链行必须脚本化（服务器上已临时落了 `/root/policy-pipeline-state/bin/commentary_signals.run_nightly.sh`，内容见 `docs/handoffs/2026-06-11-codex-wp3b-report.md` 续跑节）。本包把脚本模式收编进 repo。

**纪律（红线，违者中止）**：既有未跟踪文件不碰不提交；不合 main、不 push，分支留审计；凭据值不打印不进 git；不碰 vault。shell 脚本无 pytest 要求，但必须 `bash -n` 语法验证 + 每个 python 调用的 flag 与对应模块 argparse 逐一核对（在回报中列出核对结果）。

**分支**：`wp4/contexts-nightly`（从 main `9c5a722` 起）。

## 改动 1 · 收编 03:00 信号链脚本进 repo

新建 `scripts/service/signals_nightly.sh`：内容=WP-3b report 续跑节里已验证的脚本（flock + 四段 + 白名单 push + notify），逐字保留逻辑。

## 改动 2 · 新建 03:30 上下文链脚本

新建 `scripts/service/contexts_nightly.sh`，同模式（flock 同一把锁 `/var/lock/policy-pipeline-producer.lock`、notify.env、失败 notify "[S2] 03:30 上下文链失败,查 contexts.log"），链：

1. `docker compose ... run --rm policy-producer python -m scripts.signal_context preview --vault /vault --state /state/signal_context/nightly --blocked-signals /state/derived_signals/nightly/blocked_signals.jsonl`（入口形式 `-m scripts.signal_context` 还是 `.run` 以代码为准）
2. `... python -m scripts.analysis_context preview --relations <以测试/设计为准：应为 /vault/1_extracted/relations/relations_canonical.jsonl 或模块期望的输入> --policy-context /state/signal_context/nightly/policy_context.jsonl --state /state/analysis_layer/nightly`
3. `... python -m scripts.analysis_relation_inventory preview --vault /vault --state /state/analysis_layer/nightly_inventory`

注意核对：各模块对已存在 state 目录的行为（每晚覆盖是否安全；若模块要求空目录，脚本里先 `rm -rf` 对应 nightly 目录再跑——只许删这三个 nightly 路径）。

## 改动 3 · runbook 更新

`docs/runbooks/s2-vps-cron.md`：
- 03:00 行改为短行：`0 3 * * * /root/policy-pipeline-src/scripts/service/signals_nightly.sh >> /var/log/policy-pipeline/signals.log 2>&1`，注明脚本文件是逻辑唯一真相源、服务器临时脚本 `/root/policy-pipeline-state/bin/` 待 WP-4b 移除；
- 新增 03:30 行：`30 3 * * * /root/policy-pipeline-src/scripts/service/contexts_nightly.sh >> /var/log/policy-pipeline/contexts.log 2>&1`；
- 备注：上下文链产物在 /state 非 vault，无 push 环节；每晚覆盖重建。

## 验证（本地）

`bash -n` 两脚本；flag 核对清单（脚本每个 CLI 调用 vs argparse 定义）；`python3 -m pytest` 全绿（585 基线，本包不该动 python 代码——若发现必须改 python 才能接通，停下报告）。

## 回报

stdout 回报：分支、commit 列表、bash -n 结果、flag 核对清单、--relations 实际采用的输入路径及依据。无需 report 文件。
