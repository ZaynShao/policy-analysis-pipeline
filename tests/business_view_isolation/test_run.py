import json
from pathlib import Path

import yaml

from scripts.business_view_isolation.run import run_apply, run_dryrun


def _write_bv(vault: Path, pid: str, data: dict) -> Path:
    out = vault / "_meta" / "business_view"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{pid}.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_dryrun_writes_manifest_summary_and_html(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    _write_bv(vault, "P_2026_OK_1", {
        "pid": "P_2026_OK_1",
        "extracted_by": "scripts/l2_themescore/run_2b.py",
        "影响分析": {"加油": "a", "充电": "b", "电力_储能_V2G_交易": "c"},
    })
    _write_bv(vault, "P_2025_OLD_1", {
        "pid": "P_2025_OLD_1",
        "extracted_by": "_meta/scripts/oneshot_apply_5c_subagent_results.py",
        "影响分析": {"加油": "a", "充电": "b", "电力_储能_V2G_交易": "c", "乡村": "old"},
    })

    result = run_dryrun(vault, state)

    assert result["summary"]["by_action"] == {"isolate_legacy": 1, "keep_current": 1}
    assert (state / "manifest.jsonl").exists()
    assert (state / "summary.json").exists()
    assert (state / "reports" / "business_view_isolation.html").exists()
    rows = [json.loads(line) for line in (state / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["pid"] == "P_2025_OLD_1"
    html = (state / "reports" / "business_view_isolation.html").read_text(encoding="utf-8")
    assert "旧 business_view 消费隔离 dry-run" in html
    assert "不写资料库" in html


def test_dryrun_does_not_modify_vault_files(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    path = _write_bv(vault, "P_2025_OLD_1", {
        "pid": "P_2025_OLD_1",
        "extracted_by": "unknown_legacy",
        "影响分析": {"加油": "a", "乡村": "old"},
    })
    before = path.read_text(encoding="utf-8")

    run_dryrun(vault, state)

    assert path.read_text(encoding="utf-8") == before


def test_apply_backs_up_and_removes_only_isolate_legacy(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    backup = tmp_path / "backup"
    old_path = _write_bv(vault, "P_2025_OLD_1", {
        "pid": "P_2025_OLD_1",
        "extracted_by": "_meta/scripts/oneshot_apply_5c_subagent_results.py",
        "影响分析": {"加油": "a", "乡村": "old"},
    })
    current_path = _write_bv(vault, "P_2026_OK_1", {
        "pid": "P_2026_OK_1",
        "extracted_by": "scripts/l2_themescore/run_2b.py",
        "影响分析": {"加油": "a", "充电": "b", "电力_储能_V2G_交易": "c"},
    })
    old_text = old_path.read_text(encoding="utf-8")

    run_dryrun(vault, state)
    result = run_apply(vault, state, backup)

    assert result["summary"]["applied"] == 1
    assert result["summary"]["skipped_keep_current"] == 1
    assert not old_path.exists()
    assert current_path.exists()
    backup_path = backup / "_meta" / "business_view" / "P_2025_OLD_1.yaml"
    assert backup_path.read_text(encoding="utf-8") == old_text
    assert (state / "apply_log.jsonl").exists()
    assert (state / "reports" / "business_view_isolation_apply.html").exists()


def test_apply_refuses_backup_inside_vault(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    _write_bv(vault, "P_2025_OLD_1", {
        "pid": "P_2025_OLD_1",
        "extracted_by": "unknown_legacy",
        "影响分析": {"加油": "a", "乡村": "old"},
    })

    run_dryrun(vault, state)

    try:
        run_apply(vault, state, vault / "_backup")
    except ValueError as exc:
        assert "backup_dir must be outside vault" in str(exc)
    else:
        raise AssertionError("expected backup path guard")
