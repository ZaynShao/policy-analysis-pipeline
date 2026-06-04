import json

import pytest

from scripts.derived_signals.run import apply_preview, build_preview


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_preview_writes_only_signal_rows_and_reports_queue_counts(tmp_path):
    commentary_state = tmp_path / "commentary"
    market_state = tmp_path / "market"
    preview_state = tmp_path / "preview"

    _write_jsonl(
        commentary_state / "signals.jsonl",
        [
            {
                "commentary_id": "C_1",
                "path": "评论.md",
                "title": "电价风险解读",
                "related_policy_ids": ["P_1"],
                "theme_ids": ["power_market"],
                "signal_role": "risk",
                "evidence": "电价波动带来不确定性。",
            }
        ],
    )
    _write_jsonl(
        commentary_state / "review_queue.jsonl",
        [
            {
                "commentary_id": "C_QUEUE",
                "path": "待判.md",
                "title": "待人工判定",
                "reason": "linked_commentary_without_theme_hit",
            }
        ],
    )
    _write_jsonl(
        market_state / "market_signals.jsonl",
        [
            {
                "market_signal_id": "MI_1",
                "source_pid": "P_MI",
                "current_policy_id": "P_MI",
                "raw_path": "项目清单.md",
                "title": "储能项目清单",
                "theme_ids": ["energy_storage_theme"],
                "business_lines": ["power"],
                "signal_type": "project_list",
                "evidence": "公示储能项目。",
            }
        ],
    )
    _write_jsonl(
        market_state / "review_queue.jsonl",
        [
            {
                "source_pid": "P_QUEUE",
                "title": "待人工判断地区",
                "reason": "region_unknown",
            }
        ],
    )

    result = build_preview(commentary_state, market_state, preview_state)

    assert result["summary"]["commentary_signals"] == 1
    assert result["summary"]["market_intel_signals"] == 1
    assert result["summary"]["commentary_review_queue"] == 1
    assert result["summary"]["market_intel_review_queue"] == 1

    commentary_rows = _read_jsonl(preview_state / "commentary_signals.jsonl")
    market_rows = _read_jsonl(preview_state / "market_intel_signals.jsonl")

    assert [row["commentary_id"] for row in commentary_rows] == ["C_1"]
    assert commentary_rows[0]["schema_version"] == 1
    assert commentary_rows[0]["source_kind"] == "commentary"
    assert commentary_rows[0]["sanitized_from"] == "0_raw/commentaries/评论.md"
    assert [row["market_signal_id"] for row in market_rows] == ["MI_1"]
    assert market_rows[0]["source_kind"] == "market_intel"
    assert market_rows[0]["sanitized_from"] == "0_raw/policies/项目清单.md"

    summary = json.loads((preview_state / "summary.json").read_text(encoding="utf-8"))
    assert summary["will_write"] == [
        "1_extracted/commentary_signals.jsonl",
        "1_extracted/market_intel_signals.jsonl",
    ]
    html = (preview_state / "reports" / "derived_signals_preview.html").read_text(encoding="utf-8")
    assert "派生信号 preview" in html
    assert "不写资料库" in html
    assert "不消费人工池" in html


def test_preview_blocks_signal_rows_that_overlap_review_queue(tmp_path):
    commentary_state = tmp_path / "commentary"
    market_state = tmp_path / "market"
    preview_state = tmp_path / "preview"

    _write_jsonl(
        commentary_state / "signals.jsonl",
        [
            {"commentary_id": "C_BLOCK", "path": "待判评论.md", "title": "待判评论"},
            {"commentary_id": "C_ACCEPT", "path": "通过评论.md", "title": "通过评论"},
        ],
    )
    _write_jsonl(
        commentary_state / "review_queue.jsonl",
        [
            {
                "commentary_id": "C_BLOCK",
                "path": "待判评论.md",
                "title": "待判评论",
                "reason": "linked_commentary_without_theme_hit",
            }
        ],
    )
    _write_jsonl(
        market_state / "market_signals.jsonl",
        [
            {
                "market_signal_id": "MI_BLOCK",
                "source_pid": "P_SOURCE",
                "current_policy_id": "P_CURRENT",
                "raw_path": "待判项目.md",
                "title": "待判项目",
            },
            {
                "market_signal_id": "MI_ACCEPT",
                "source_pid": "P_OK",
                "current_policy_id": "P_OK",
                "raw_path": "通过项目.md",
                "title": "通过项目",
            },
        ],
    )
    _write_jsonl(
        market_state / "review_queue.jsonl",
        [
            {
                "source_pid": "P_SOURCE",
                "current_policy_id": "P_CURRENT",
                "raw_path": "待判项目.md",
                "title": "待判项目",
                "reason": "theme_not_found",
            },
            {
                "source_pid": "P_SOURCE",
                "current_policy_id": "P_CURRENT",
                "raw_path": "待判项目.md",
                "title": "待判项目",
                "reason": "region_unknown",
            },
        ],
    )

    result = build_preview(commentary_state, market_state, preview_state)

    assert result["summary"]["commentary_signals"] == 1
    assert result["summary"]["market_intel_signals"] == 1
    assert result["summary"]["blocked_signals"] == 2
    assert result["summary"]["blocked_commentary_signals"] == 1
    assert result["summary"]["blocked_market_intel_signals"] == 1

    commentary_rows = _read_jsonl(preview_state / "commentary_signals.jsonl")
    market_rows = _read_jsonl(preview_state / "market_intel_signals.jsonl")
    blocked_rows = _read_jsonl(preview_state / "blocked_signals.jsonl")

    assert [row["commentary_id"] for row in commentary_rows] == ["C_ACCEPT"]
    assert [row["market_signal_id"] for row in market_rows] == ["MI_ACCEPT"]
    assert {(row["source_kind"], row["block_key"]) for row in blocked_rows} == {
        ("commentary", "C_BLOCK"),
        ("market_intel", "P_SOURCE|P_CURRENT|待判项目.md"),
    }
    market_block = next(row for row in blocked_rows if row["source_kind"] == "market_intel")
    assert market_block["queue_reasons"] == ["region_unknown", "theme_not_found"]


def test_apply_writes_only_1_extracted_from_preview(tmp_path):
    commentary_state = tmp_path / "commentary"
    market_state = tmp_path / "market"
    preview_state = tmp_path / "preview"
    vault = tmp_path / "vault"
    raw_path = vault / "0_raw" / "policies" / "keep.md"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text("raw stays unchanged", encoding="utf-8")

    _write_jsonl(commentary_state / "signals.jsonl", [{"commentary_id": "C_1", "path": "评论.md"}])
    _write_jsonl(commentary_state / "review_queue.jsonl", [{"commentary_id": "C_QUEUE"}])
    _write_jsonl(market_state / "market_signals.jsonl", [{"market_signal_id": "MI_1", "raw_path": "项目.md"}])
    _write_jsonl(market_state / "review_queue.jsonl", [{"source_pid": "P_QUEUE"}])
    build_preview(commentary_state, market_state, preview_state)

    result = apply_preview(vault, preview_state)

    assert result["summary"]["written"] == [
        "1_extracted/commentary_signals.jsonl",
        "1_extracted/market_intel_signals.jsonl",
    ]
    assert (vault / "1_extracted" / "commentary_signals.jsonl").exists()
    assert (vault / "1_extracted" / "market_intel_signals.jsonl").exists()
    assert raw_path.read_text(encoding="utf-8") == "raw stays unchanged"
    assert (preview_state / "apply_summary.json").exists()
    assert (preview_state / "apply_log.jsonl").exists()
    assert (preview_state / "reports" / "derived_signals_apply.html").exists()


def test_apply_refuses_missing_preview(tmp_path):
    with pytest.raises(FileNotFoundError):
        apply_preview(tmp_path / "vault", tmp_path / "missing_preview")
