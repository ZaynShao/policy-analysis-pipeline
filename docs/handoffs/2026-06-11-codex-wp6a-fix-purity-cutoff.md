# Codex 交接：WP-6a-fix 巡检纯净检查加时代分界线（本地代码侧，小包）

**背景**：WP-6b dry-run 报 2 项假阳性——近 20 commit 窗口扫到 6/6、6/7 的迁移前历史 commit（ZaynShao 作者触产物路径）。这些是单生产者纪律生效（2026-06-11）**之前**的合法 Mac 时代 commit。

**修复设计**：`closure_audit.py` 加常量 `PURITY_CUTOFF = "2026-06-11T00:00:00+08:00"`（含注释：单生产者时代分界，之前的 commit 豁免作者检查）。`check_vault_git` 取每个 commit 的 author date（`%aI`），早于 cutoff 的跳过作者检查；脏树/HEAD 漂移检查不受影响。

**纪律（红线）**：TDD 红绿分 commit；只许改 `scripts/service/closure_audit.py` + `tests/service/test_closure_audit.py`；不合 main 不 push；既有未跟踪文件不碰。

**分支**：`wp6/purity-cutoff`（从 main `74ff6d7` 起）。

## 测试（红先行）

- cutoff 前的非 vps 作者产物 commit → 不告警；
- cutoff 后的非 vps 作者产物 commit → 告警（既有行为回归）；
- git 夹具用 `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` 环境变量造历史日期 commit。

## 验证

`python3 -m pytest` 全绿（602 基线+新增）。

## 回报

stdout：分支、红绿 commit、pytest 数字。无需 report 文件。
