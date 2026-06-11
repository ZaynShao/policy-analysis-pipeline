# Codex 交接：WP-6a 闭环审计日巡检（本地代码侧）

**背景**：云上闭环已成（②bv/registry + ③relations/signals + ④contexts 备料），本包建"忘了上云=告警而非回忆测验"的日巡检。**模式照抄 `scripts/service/deadletter_alert.py`**（host python 只读 + notify，已有同款测试先例）。

**纪律（红线，违者中止）**：TDD 红绿分 commit；只许新建 `scripts/service/closure_audit.py` + `tests/service/test_closure_audit.py` + runbook 一行；既有未跟踪文件不碰；不合 main 不 push；不碰 vault；凭据值盲。

**分支**：`wp6/closure-audit`（从 main `8817d1c` 起）。

## 模块设计 `closure_audit.py`

CLI：`python -m scripts.service.closure_audit --vault V --state-dir S [--dry-run]`（--dry-run=只打印不 notify）。

### 检查 A · 生产活性（state mtime，判"产线昨晚/今晨跑过"）

内置阈值表（路径相对 state-dir，小时）：

| state 路径 | 阈值 | 对应产线 |
|---|---|---|
| `commentary_ingest/last_run.json` | 26 | 07:30 评论 ingest |
| `relations_increment/hpr` | 26 | 02:00 关系增量（0 新 pid 也会刷 hpr 扫描）|
| `derived_signals/nightly` | 26 | 03:00 信号链 |
| `signal_context/nightly` | 26 | 03:30 上下文链 |
| `analysis_layer/nightly` | 26 | 03:30 上下文链 |
| `last_sync_run.json` | 26 | 投影 |

缺失或 mtime 超龄 → 违规项。另：`last_sync_run.json` 内容 `errors` 非空 → 违规项。

### 检查 B · 生产纯净（vault git，判"没人云外偷生产"）

- vault 工作树必须干净 且 HEAD==origin/main（`git status --porcelain` 空 + rev-parse 比对；**只读命令**）；
- 最近 20 个 commit 中，凡触及产物路径（`0_raw/`、`1_extracted/`、`_meta/business_view/`）的 commit，作者必须 == `policy-pipeline-vps`，否则违规（报 commit hash+作者+路径示例）。

### 输出

- 违规列表非空 → `send_text("[S2] 闭环巡检异常 N 项: <逐项一行>")`（notify 用法照 deadletter_alert）+ exit 1；
- 全绿 → stdout 一行 JSON `{"ok": true, "checked": ...}`，**不 notify**（静默=健康），exit 0。

## runbook

§1 加一行（host python 只读，不持锁）：
`45 10 * * * cd /root/policy-pipeline-src && (set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.closure_audit --vault /root/policy-vault --state-dir /root/policy-pipeline-state) >> /var/log/policy-pipeline/closure_audit.log 2>&1`
（行长安全，无需脚本化；如实测格式有出入以 deadletter_alert 既有行风格为准。）

## 测试要求（红先行）

tmp 目录夹具：mtime 新/旧/缺失三态；errors 非空；git 夹具仓（init+commit 可在 tmp 内做）验证脏树/HEAD 漂移/非 vps 作者触产物路径/非产物路径的非 vps commit 不告警；--dry-run 不调 notify（mock send_text 计数）；全绿时不调 notify。

## 验证

`python3 -m pytest` 全绿（594 基线+新增）。

## 回报

stdout：分支、红绿 commit、pytest 数字。无需 report 文件。
