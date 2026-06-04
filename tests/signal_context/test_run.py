import json

import pytest

from scripts.signal_context.run import run_preview


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _commentary(cid, policies, themes, role):
    return {
        "commentary_id": cid,
        "title": f"评论 {cid}",
        "related_policy_ids": policies,
        "theme_ids": themes,
        "signal_role": role,
        "confidence": 0.7,
        "source_kind": "commentary",
    }


def _market(mid, current_policy, themes, signal_type, region=None, related=None):
    return {
        "market_signal_id": mid,
        "current_policy_id": current_policy,
        "related_policy_ids": related or [],
        "title": f"市场 {mid}",
        "theme_ids": themes,
        "business_lines": ["power"],
        "signal_type": signal_type,
        "region": region or {"level": "省", "code": "110000", "name": "北京市"},
        "observed_date": "2026-01-01",
        "confidence": 0.9,
        "source_kind": "market_intel",
    }


def _fixture_vault(tmp_path, commentary_rows, market_rows):
    vault = tmp_path / "vault"
    _write_jsonl(vault / "1_extracted" / "commentary_signals.jsonl", commentary_rows)
    _write_jsonl(vault / "1_extracted" / "market_intel_signals.jsonl", market_rows)
    return vault


def test_policy_context_aggregates_roles_market_types_and_refs(tmp_path):
    vault = _fixture_vault(
        tmp_path,
        [
            _commentary("C_1", ["P_1"], ["t_power"], "risk"),
            _commentary("C_2", ["P_1"], ["t_power"], "opportunity"),
        ],
        [
            _market("MI_1", "P_1", ["t_power"], "project_list"),
            _market("MI_2", "P_2", ["t_market_only"], "market_access", related=["P_1"]),
        ],
    )

    result = run_preview(vault, tmp_path / "state", blocked_signals_path=None)

    assert result["summary"]["accepted_commentary_signals"] == 2
    assert result["summary"]["accepted_market_signals"] == 2
    policy_rows = _read_jsonl(tmp_path / "state" / "policy_context.jsonl")
    p1 = next(row for row in policy_rows if row["policy_id"] == "P_1")
    assert p1["commentary_signal_count"] == 2
    assert p1["market_signal_count"] == 2
    assert p1["commentary_roles"] == {"opportunity": 1, "risk": 1}
    assert p1["market_signal_types"] == {"market_access": 1, "project_list": 1}
    assert p1["attention_level"] == "medium"
    assert p1["validation_level"] == "medium"
    assert p1["certainty_adjustment"] == "neutral"
    assert set(p1["audit_refs"]["commentary_ids"]) == {"C_1", "C_2"}
    assert set(p1["audit_refs"]["market_signal_ids"]) == {"MI_1", "MI_2"}


def test_theme_and_region_context_warnings(tmp_path):
    vault = _fixture_vault(
        tmp_path,
        [_commentary("C_1", ["P_1"], ["commentary_only_theme", "mixed_theme"], "execution")],
        [
            _market("MI_1", "P_2", ["market_only_theme"], "pilot_landing"),
            _market("MI_2", "P_3", ["mixed_theme"], "project_case"),
        ],
    )

    run_preview(vault, tmp_path / "state", blocked_signals_path=None)

    theme_rows = _read_jsonl(tmp_path / "state" / "theme_context.jsonl")
    by_theme = {row["theme_id"]: row for row in theme_rows}
    assert by_theme["commentary_only_theme"]["coverage_warning"] == "commentary_only"
    assert by_theme["market_only_theme"]["coverage_warning"] == "market_only"
    assert by_theme["mixed_theme"]["coverage_warning"] == "none"
    assert by_theme["mixed_theme"]["dominant_commentary_roles"] == ["execution"]
    assert by_theme["market_only_theme"]["dominant_market_signal_types"] == ["pilot_landing"]

    region_rows = _read_jsonl(tmp_path / "state" / "region_context.jsonl")
    assert len(region_rows) == 1
    assert region_rows[0]["region_code"] == "110000"
    assert region_rows[0]["market_signal_count"] == 2
    assert region_rows[0]["region_warnings"] == []


def test_blocked_ids_fail_and_unknown_region_is_excluded(tmp_path):
    vault = _fixture_vault(
        tmp_path,
        [_commentary("C_BLOCKED", ["P_1"], ["t_power"], "risk")],
        [
            _market(
                "MI_UNKNOWN",
                "P_1",
                ["t_power"],
                "project_list",
                region={"level": "", "code": "", "name": ""},
            )
        ],
    )
    blocked = tmp_path / "blocked.jsonl"
    _write_jsonl(blocked, [{"commentary_id": "C_BLOCKED", "source_kind": "commentary"}])

    with pytest.raises(ValueError, match="blocked signal"):
        run_preview(vault, tmp_path / "blocked_state", blocked_signals_path=blocked)

    result = run_preview(vault, tmp_path / "state", blocked_signals_path=None)
    assert result["summary"]["unknown_region_market_signals"] == 1
    assert _read_jsonl(tmp_path / "state" / "region_context.jsonl") == []


def test_region_context_flags_code_name_granularity_mismatch(tmp_path):
    vault = _fixture_vault(
        tmp_path,
        [],
        [
            _market(
                "MI_MISMATCH",
                "P_1",
                ["t_power"],
                "pilot_landing",
                region={"level": "市", "code": "130000", "name": "唐山市"},
            )
        ],
    )

    result = run_preview(vault, tmp_path / "state", blocked_signals_path=None)

    region_rows = _read_jsonl(tmp_path / "state" / "region_context.jsonl")
    assert region_rows[0]["region_warnings"] == ["province_code_with_city_name"]
    assert result["summary"]["region_warning_count"] == 1


def test_preview_outputs_files_and_boundary_html(tmp_path):
    vault = _fixture_vault(
        tmp_path,
        [_commentary("C_1", ["P_1"], ["t_power"], "risk")],
        [_market("MI_1", "P_1", ["t_power"], "project_list")],
    )

    run_preview(vault, tmp_path / "state", blocked_signals_path=None)

    for name in ["policy_context.jsonl", "theme_context.jsonl", "region_context.jsonl", "summary.json"]:
        assert (tmp_path / "state" / name).exists()
    html = (tmp_path / "state" / "reports" / "signal_context_preview.html").read_text(encoding="utf-8")
    assert "不写资料库" in html
    assert "不读取 blocked signals 当 accepted" in html
    assert "注入" not in html
