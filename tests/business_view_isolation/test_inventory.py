from pathlib import Path

import yaml

from scripts.business_view_isolation.inventory import (
    EXPECTED_IMPACT_KEYS,
    inspect_business_view,
    inventory_business_views,
    summarize,
)


def _write_bv(vault: Path, pid: str, data: dict, raw_text: str = None) -> Path:
    out = vault / "_meta" / "business_view"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{pid}.yaml"
    if raw_text is None:
        raw_text = yaml.dump(data, allow_unicode=True, sort_keys=False)
    path.write_text(raw_text, encoding="utf-8")
    return path


def test_classifies_current_flow_as_keep(tmp_path):
    path = _write_bv(tmp_path, "P_2026_OK_1", {
        "pid": "P_2026_OK_1",
        "extracted_by": "scripts/l2_themescore/run_2b.py",
        "extracted_model": "MiniMax-M2.7+judge-crosscheck+manual-review+v11-global-hardening",
        "影响分析": {key: "ok" for key in sorted(EXPECTED_IMPACT_KEYS)},
    })

    decision = inspect_business_view(path, tmp_path)

    assert decision.action == "keep_current"
    assert decision.reasons == ["current_flow"]
    assert set(decision.impact_keys) == EXPECTED_IMPACT_KEYS


def test_classifies_legacy_xiangcun_as_isolate(tmp_path):
    path = _write_bv(tmp_path, "P_2025_OLD_1", {
        "pid": "P_2025_OLD_1",
        "extracted_by": "_meta/scripts/oneshot_apply_5c_subagent_results.py",
        "extracted_model": "claude-opus-4-7-via-subagent",
        "影响分析": {
            "加油": "a",
            "充电": "b",
            "电力_储能_V2G_交易": "c",
            "乡村": "old",
        },
    })

    decision = inspect_business_view(path, tmp_path)

    assert decision.action == "isolate_legacy"
    assert "legacy_extracted_by" in decision.reasons
    assert "deprecated_xiangcun_key" in decision.reasons


def test_unparseable_yaml_goes_to_manual_review(tmp_path):
    path = _write_bv(tmp_path, "P_2025_BAD_1", {}, raw_text="pid: [broken\n")

    decision = inspect_business_view(path, tmp_path)

    assert decision.action == "manual_review"
    assert any(reason.startswith("yaml_parse_error") for reason in decision.reasons)
    assert decision.pid == "P_2025_BAD_1"


def test_inventory_and_summary_count_actions(tmp_path):
    _write_bv(tmp_path, "P_2026_OK_1", {
        "pid": "P_2026_OK_1",
        "extracted_by": "scripts/l2_themescore/run_2b.py",
        "extracted_model": "MiniMax-M2.7",
        "影响分析": {"加油": "a", "充电": "b", "电力_储能_V2G_交易": "c"},
    })
    _write_bv(tmp_path, "P_2025_OLD_1", {
        "pid": "P_2025_OLD_1",
        "extracted_by": "unknown_legacy",
        "影响分析": {"加油": "a", "乡村": "old"},
    })

    decisions = inventory_business_views(tmp_path)
    summary = summarize(decisions)

    assert [d.pid for d in decisions] == ["P_2025_OLD_1", "P_2026_OK_1"]
    assert summary["total"] == 2
    assert summary["by_action"] == {"isolate_legacy": 1, "keep_current": 1}
    assert summary["by_reason"]["deprecated_xiangcun_key"] == 1
    assert summary["by_extracted_model"]["MiniMax-M2.7"] == 1
    assert summary["by_extracted_model"][""] == 1
