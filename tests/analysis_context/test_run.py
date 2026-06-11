import json

import pytest

from scripts.analysis_context.run import run_preview


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _relation(candidate_id, source, target, rel):
    return {
        "candidate_id": candidate_id,
        "from": source,
        "to": target,
        "rel": rel,
        "confidence": 0.9,
    }


def _canonical_relation(edge_id, source, target, rel):
    return {
        "from": source,
        "to": target,
        "rel": rel,
        "confidence": 0.9,
        "evidence": {"snippet": "edge evidence"},
        "source": edge_id,
    }


def _signal_row(policy_id):
    return {
        "policy_id": policy_id,
        "commentary_signal_count": 2,
        "market_signal_count": 1,
        "attention_level": "medium",
        "validation_level": "weak",
        "certainty_adjustment": "lower",
        "internal_notes": ["commentary_risk_present", "market_validation_weak"],
        "audit_refs": {
            "commentary_ids": ["C_1", "C_2"],
            "market_signal_ids": ["MI_1"],
        },
    }


def _rows_by_policy(path):
    return {row["policy_id"]: row for row in _read_jsonl(path)}


def test_analysis_context_merges_relation_and_signal_summaries(tmp_path):
    relations = tmp_path / "relations.jsonl"
    policy_context = tmp_path / "policy_context.jsonl"
    state = tmp_path / "state"
    _write_jsonl(
        relations,
        [
            _relation("HPR_basis", "P_A", "P_B", "cites_basis"),
            _relation("HPR_sup", "P_C", "P_A", "supersedes"),
            _relation("HPR_clarify", "P_A", "P_D", "clarifies"),
        ],
    )
    _write_jsonl(policy_context, [_signal_row("P_A")])

    result = run_preview(relations, policy_context, state)

    p_a = _rows_by_policy(state / "analysis_context.jsonl")["P_A"]
    assert p_a["relation_summary"]["cites_basis_out"] == 1
    assert p_a["relation_summary"]["superseded_by_count"] == 1
    assert p_a["relation_summary"]["clarifies_out"] == 1
    assert p_a["signal_summary"]["commentary_signal_count"] == 2
    assert p_a["signal_summary"]["market_signal_count"] == 1
    assert p_a["signal_summary"]["commentary_attention"] == "medium"
    assert p_a["signal_summary"]["market_validation"] == "weak"
    assert p_a["signal_summary"]["certainty_adjustment"] == "lower"
    assert set(p_a["audit_refs"]["relation_candidate_ids"]) == {"HPR_basis", "HPR_sup", "HPR_clarify"}
    assert set(p_a["audit_refs"]["commentary_ids"]) == {"C_1", "C_2"}
    assert set(p_a["audit_refs"]["market_signal_ids"]) == {"MI_1"}
    assert {
        "has_basis_chain",
        "superseded_by_policy",
        "has_clarification",
        "commentary_attention_medium",
        "market_validation_weak",
        "certainty_lower",
    } <= set(p_a["analysis_flags"])
    assert result["summary"]["rows_with_both"] == 1


def test_analysis_context_keeps_relation_only_and_signal_only_rows(tmp_path):
    relations = tmp_path / "relations.jsonl"
    policy_context = tmp_path / "policy_context.jsonl"
    state = tmp_path / "state"
    _write_jsonl(relations, [_relation("HPR_ref", "P_REL_FROM", "P_REL_TO", "references")])
    _write_jsonl(policy_context, [_signal_row("P_SIGNAL")])

    result = run_preview(relations, policy_context, state)

    rows = _rows_by_policy(state / "analysis_context.jsonl")
    assert {"P_REL_FROM", "P_REL_TO", "P_SIGNAL"} <= set(rows)
    assert "relation_only_no_signal_context" in rows["P_REL_FROM"]["analysis_flags"]
    assert "relation_only_no_signal_context" in rows["P_REL_TO"]["analysis_flags"]
    assert "signal_only_no_relation_context" in rows["P_SIGNAL"]["analysis_flags"]
    assert result["summary"]["rows_with_relation_context"] == 2
    assert result["summary"]["rows_with_signal_context"] == 1


def test_analysis_context_accepts_canonical_relation_source_as_candidate_id(tmp_path):
    relations = tmp_path / "relations.jsonl"
    policy_context = tmp_path / "policy_context.jsonl"
    state = tmp_path / "state"
    _write_jsonl(
        relations,
        [
            _canonical_relation("SRC_aligns", "P_A", "P_B", "aligns_with"),
            _canonical_relation("SRC_derives", "P_B", "P_C", "derives_from"),
        ],
    )
    _write_jsonl(policy_context, [])

    result = run_preview(relations, policy_context, state)

    rows = _rows_by_policy(state / "analysis_context.jsonl")
    assert rows["P_A"]["relation_summary"]["other_rel_counts"] == {"aligns_with": 1}
    assert rows["P_B"]["relation_summary"]["other_rel_counts"] == {
        "aligns_with": 1,
        "derives_from": 1,
    }
    assert rows["P_C"]["relation_summary"]["other_rel_counts"] == {"derives_from": 1}
    assert rows["P_A"]["audit_refs"]["relation_candidate_ids"] == ["SRC_aligns"]
    assert rows["P_B"]["audit_refs"]["relation_candidate_ids"] == ["SRC_aligns", "SRC_derives"]
    assert result["summary"]["rel_vocabulary_seen"] == {"aligns_with": 1, "derives_from": 1}


def test_analysis_context_keeps_legacy_relation_counts_unchanged(tmp_path):
    relations = tmp_path / "relations.jsonl"
    policy_context = tmp_path / "policy_context.jsonl"
    state = tmp_path / "state"
    _write_jsonl(relations, [_relation("HPR_ref", "P_A", "P_B", "references")])
    _write_jsonl(policy_context, [])

    run_preview(relations, policy_context, state)

    rows = _rows_by_policy(state / "analysis_context.jsonl")
    assert rows["P_A"]["relation_summary"]["references_out"] == 1
    assert rows["P_B"]["relation_summary"]["references_in"] == 1
    assert rows["P_A"]["audit_refs"]["relation_candidate_ids"] == ["HPR_ref"]


def test_analysis_context_rejects_relation_rows_without_required_fields(tmp_path):
    relations = tmp_path / "relations.jsonl"
    policy_context = tmp_path / "policy_context.jsonl"
    state = tmp_path / "state"
    _write_jsonl(relations, [{"from": "P_A", "to": "P_B", "rel": "references"}])
    _write_jsonl(policy_context, [])

    with pytest.raises(ValueError, match="candidate_id"):
        run_preview(relations, policy_context, state)


def test_analysis_context_keeps_unknown_relation_types_visible_without_raising(tmp_path):
    relations = tmp_path / "relations.jsonl"
    policy_context = tmp_path / "policy_context.jsonl"
    state = tmp_path / "state"
    _write_jsonl(relations, [_canonical_relation("SRC_future", "P_A", "P_B", "future_rel")])
    _write_jsonl(policy_context, [])

    result = run_preview(relations, policy_context, state)

    rows = _rows_by_policy(state / "analysis_context.jsonl")
    assert rows["P_A"]["relation_summary"]["other_rel_counts"] == {"future_rel": 1}
    assert rows["P_B"]["relation_summary"]["other_rel_counts"] == {"future_rel": 1}
    assert rows["P_A"]["audit_refs"]["relation_candidate_ids"] == ["SRC_future"]
    assert result["summary"]["rel_vocabulary_seen"] == {"future_rel": 1}


def test_preview_outputs_files_and_boundary_html(tmp_path):
    relations = tmp_path / "relations.jsonl"
    policy_context = tmp_path / "policy_context.jsonl"
    state = tmp_path / "state"
    _write_jsonl(relations, [_relation("HPR_basis", "P_A", "P_B", "cites_basis")])
    _write_jsonl(policy_context, [_signal_row("P_A")])

    run_preview(relations, policy_context, state)

    assert (state / "analysis_context.jsonl").exists()
    assert (state / "analysis_context_summary.json").exists()
    html = (state / "reports" / "analysis_context_preview.html").read_text(encoding="utf-8")
    assert "不写资料库" in html
    assert "不调用模型" in html
    assert "不是最终业务洞察" in html
    assert "④ 默认读取 analysis_context" in html
    banned_word = "注" + "入"
    assert banned_word not in html
