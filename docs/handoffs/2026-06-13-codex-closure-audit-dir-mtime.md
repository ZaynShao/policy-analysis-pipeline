# Codex 交接：闭环巡检目录新鲜度改用"内容最新 mtime"（本地代码侧）

**背景**：`scripts/service/closure_audit.py` 的 `check_state_activity` 用 `path.stat().st_mtime` 判活。对**目录**类目标(如 `relations_increment/hpr`、`derived_signals/nightly`),夜链**原地覆盖**目录内文件→目录自身 mtime 不更新→误报"超龄"。实测:目录 mtime 停在 06-11(建目录日),但内部文件 06-13 02:00/03:00 刚刷新。导致首次实战 10:45 巡检发 2 项假阳性告警。误报比漏报危险(告警疲劳),必修。

**修复**:目录类目标取**目录内所有文件的最新 mtime**(递归)作为新鲜度;文件类目标保持自身 mtime。缺失路径仍判违规。

**纪律(红线)**:TDD 红绿分 commit;只许改 `scripts/service/closure_audit.py` + `tests/service/test_closure_audit.py`;既有未跟踪文件不碰;不合 main 不 push;不碰 vault。

**分支**:`fix/closure-audit-dir-mtime`(从 main 最新起)。

## 改动

`check_state_activity` 里取 mtime 的逻辑抽成 helper,例如:
```python
def _freshness_mtime(path: Path) -> float | None:
    if not path.exists():
        return None
    if path.is_file():
        return path.stat().st_mtime
    # 目录:取递归内所有文件的最新 mtime;空目录回退到目录自身 mtime
    mtimes = [f.stat().st_mtime for f in path.rglob("*") if f.is_file()]
    return max(mtimes) if mtimes else path.stat().st_mtime
```
`check_state_activity` 用它替换原来的 `path.stat().st_mtime`;`None`→缺失违规;超阈值→超龄违规(消息保持原格式,含相对路径与小时数)。`last_sync_run.json` 的 errors 检查逻辑不变。

## 测试(红先行)

- **关键回归(红)**:构造一个目录,设其**目录自身 mtime 为旧**(超阈值),但**内部放一个 mtime 为新**的文件→应**不**违规(现状会违规=红)。用 `os.utime` 设 mtime。
- 目录内所有文件都旧→违规。
- 文件类目标:旧→违规,新→不违规(回归)。
- 缺失路径→违规。
- 空目录→回退目录 mtime 判定。
- 既有 closure_audit 测试不破。

## 验证

`python3 -m pytest tests/service/test_closure_audit.py -q` 全绿;`python3 -m pytest -q` 不回退。

## 回报

stdout:分支、红绿 commit、pytest 数字、helper 实现。无需 report 文件。
