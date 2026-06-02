import json

from scripts.l2_themescore.manual_review_server import (
    append_decision,
    is_manual_adjudication_stage,
    load_theme_options,
    load_review_items,
    make_decision_record,
    render_app,
)


def _state(tmp_path):
    state = tmp_path / "state"
    queue = state / "review_queue"
    reports = state / "reports"
    queue.mkdir(parents=True)
    reports.mkdir()
    row = {
        "pid": "P_A",
        "stage": "judge_reject",
        "reason": "弱提及硬挂",
        "detail": {"dim": "theme", "confidence": 0.9},
    }
    (queue / "queue.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports / "manual_review_pool_zh.html").write_text(
        """<!doctype html><html><body>
<section>
<h2><span class="pid">P_A</span> · 测试政策</h2>
<h3>关键正文片段</h3><p>正文证据</p>
<h3>人工需要判断</h3><p>应该放在哪</p>
</section>
</body></html>""",
        encoding="utf-8",
    )
    return state


def _state_with_technical_item(tmp_path):
    state = _state(tmp_path)
    tech = {
        "pid": "P_TECH",
        "stage": "program_gate",
        "reason": "影响分析结构错误",
        "detail": {},
    }
    with (state / "review_queue" / "queue.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(tech, ensure_ascii=False) + "\n")
    return state


def _registry(tmp_path):
    registry = tmp_path / "themes_registry.yaml"
    registry.write_text(
        """schema_version: 1.0
themes:
  - {id: charging_infra, zh: 充电基础设施, aliases: [充电设施]}
  - {id: residential_charging, zh: 居住区充电, aliases: [居民充电]}
""",
        encoding="utf-8",
    )
    return registry


def test_load_review_items_preserves_queue_provenance_and_evidence(tmp_path):
    state = _state(tmp_path)

    items = load_review_items(state)

    assert len(items) == 1
    assert items[0]["pid"] == "P_A"
    assert items[0]["queue_stage"] == "judge_reject"
    assert items[0]["queue_record_sha256"]
    assert "正文证据" in items[0]["evidence_html"]


def test_make_decision_record_keeps_audit_trail(tmp_path):
    state = _state(tmp_path)
    item = load_review_items(state)[0]

    record = make_decision_record(
        state,
        item,
        {
            "decision": "candidate_accept",
            "target_themes": ["charging_infra"],
            "primary_theme": "charging_infra",
            "importance": 3,
            "note": "正文直接部署充电设施",
        },
        now_iso="2026-06-02T12:00:00+08:00",
        operator="manual-test",
    )

    assert record["schema_version"] == "node2b_manual_decision.v1"
    assert record["pid"] == "P_A"
    assert record["decision"] == "candidate_accept"
    assert record["queue_record_sha256"] == item["queue_record_sha256"]
    assert record["queue_reason"] == "弱提及硬挂"
    assert record["operator"] == "manual-test"
    assert record["target_themes"] == ["charging_infra"]


def test_make_decision_record_accepts_clicked_theme_ids(tmp_path):
    state = _state(tmp_path)
    item = load_review_items(state)[0]

    record = make_decision_record(
        state,
        item,
        {
            "decision": "candidate_accept",
            "target_theme_ids": ["charging_infra", "residential_charging"],
            "primary_theme_id": "charging_infra",
        },
        now_iso="2026-06-02T12:00:00+08:00",
    )

    assert record["target_themes"] == ["charging_infra", "residential_charging"]
    assert record["primary_theme"] == "charging_infra"


def test_append_decision_writes_jsonl_in_state_only(tmp_path):
    state = _state(tmp_path)
    item = load_review_items(state)[0]
    record = make_decision_record(state, item, {"decision": "keep_manual"}, now_iso="2026-06-02T12:00:00+08:00")

    out = append_decision(state, record)

    assert out == state / "manual_decisions.jsonl"
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["pid"] == "P_A"
    assert rows[0]["decision"] == "keep_manual"


def test_render_app_exposes_reproducible_manual_flow(tmp_path):
    state = _state(tmp_path)

    html = render_app(state)

    assert "人工裁决台" in html
    assert "queue_record_sha256" in html
    assert "manual_decisions.jsonl" in html
    assert "P_A" in html
    assert "正文证据" in html


def test_load_theme_options_uses_chinese_labels(tmp_path):
    registry = _registry(tmp_path)

    options = load_theme_options(registry)

    assert options == [
        {"id": "charging_infra", "label": "充电基础设施"},
        {"id": "residential_charging", "label": "居住区充电"},
    ]


def test_render_app_uses_clickable_chinese_theme_picker(tmp_path):
    state = _state(tmp_path)
    registry = _registry(tmp_path)

    html = render_app(state, registry)

    assert "充电基础设施" in html
    assert "居住区充电" in html
    assert 'data-role="theme-option"' in html
    assert 'data-role="primary-option"' in html
    assert '<input name="target_themes"' not in html
    assert '<input name="primary_theme"' not in html


def test_only_judge_reject_enters_manual_adjudication():
    assert is_manual_adjudication_stage("judge_reject")
    assert not is_manual_adjudication_stage("program_gate")
    assert not is_manual_adjudication_stage("generation_error")


def test_render_app_separates_technical_rerun_items(tmp_path):
    state = _state_with_technical_item(tmp_path)
    registry = _registry(tmp_path)

    html = render_app(state, registry)

    assert "人工裁决项 1 条" in html
    assert "技术复跑项 1 条" in html
    assert "P_TECH" in html
    assert "影响分析结构错误" in html
    assert '"pid": "P_TECH"' not in html
