import json

from scripts.l2_themescore.manual_review_server import load_review_items, make_decision_record
from scripts.l2_themescore.manual_review_summary import build_post_review_summary, render_post_review_preview


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _state(tmp_path):
    state = tmp_path / "state"
    queue_rows = [
        {"pid": "P_MANUAL", "stage": "judge_reject", "reason": "人工判业务归属", "detail": {"dim": "theme"}},
        {"pid": "P_TECH", "stage": "program_gate", "reason": "结构错误", "detail": {}},
    ]
    _write_jsonl(state / "review_queue" / "queue.jsonl", queue_rows)
    (state / "reports").mkdir(parents=True)
    (state / "reports" / "manual_review_pool_zh.html").write_text(
        """<!doctype html><html><body>
<section><h2><span class="pid">P_MANUAL</span> · 人工项</h2><p>证据</p></section>
<section><h2><span class="pid">P_TECH</span> · 技术项</h2><p>证据</p></section>
</body></html>""",
        encoding="utf-8",
    )
    _write_jsonl(state / "proposed_changes" / "drafts_full.jsonl", [
        {
            "pid": "P_READY",
            "themes": ["charging_infra"],
            "primary_theme": "charging_infra",
            "comprehensive": False,
            "scores": {"D1": 5, "D2": 4, "D3": 3, "D4": 3, "D5": 3, "D6": 3},
            "重要性": 4,
            "行动分类": "C",
            "价值标签": ["机会"],
            "gate_passed_deep": True,
            "影响分析": {"加油": "a", "充电": "b", "电力_储能_V2G_交易": "c"},
            "行动建议": ["A 趁早:x"],
            "didi_impact_one_liner": "y",
        }
    ])
    item = load_review_items(state)[0]
    decision = make_decision_record(
        state,
        item,
        {
            "decision": "candidate_accept",
            "target_theme_ids": ["charging_infra"],
            "primary_theme_id": "charging_infra",
            "importance": 4,
            "note": "人工确认",
        },
        now_iso="2026-06-02T12:00:00+08:00",
        operator="tester",
    )
    _write_jsonl(state / "manual_decisions.jsonl", [decision])
    return state


def test_post_review_summary_keeps_manual_decisions_out_of_direct_apply(tmp_path):
    state = _state(tmp_path)

    summary = build_post_review_summary(state)

    assert summary["accepted_draft_count"] == 1
    assert summary["validated_manual_decision_count"] == 1
    assert summary["technical_rerun_count"] == 1
    assert summary["remaining_manual_count"] == 0
    assert summary["manual_decisions_direct_apply"] is False
    assert summary["validated_manual_decisions"][0]["pid"] == "P_MANUAL"
    assert summary["technical_rerun_items"][0]["pid"] == "P_TECH"


def test_render_post_review_preview_explains_next_actions(tmp_path):
    state = _state(tmp_path)
    out = state / "reports" / "post_review_preview_zh.html"

    render_post_review_preview(state, out)

    html = out.read_text(encoding="utf-8")
    assert "post-review preview" in html
    assert "原 dry-run accepted" in html
    assert "人工裁决已闭环,但不是完整 draft" in html
    assert "技术复跑项" in html
    assert "P_READY" in html
    assert "P_MANUAL" in html
    assert "P_TECH" in html
