import json, yaml
from pathlib import Path
from scripts.common.llm import LLMClient
from scripts.l2_themescore.run_2b import plan

REG = """schema_version: 1.0
themes:
  - {id: power_market, zh: 电力市场, aliases: [电力市场, 现货交易]}
  - {id: v2g, zh: 车网互动, aliases: [车网互动, V2G]}
"""
DOC = """---
id: P_T1
title: 电力现货市场建设方案
issuer: [国家发展和改革委员会]
region: {level: 国家, code: '000000', name: 全国}
provenance: {url: 'http://x'}
---
## 政策原文
推进电力现货市场,完善中长期交易。
"""

def _seq_fake(payloads):
    state = {"i": 0}
    class M:
        def create(self, **kw):
            p = payloads[min(state["i"], len(payloads)-1)]; state["i"] += 1
            class R: content=[type("B",(),{"text":p})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages=M()
    return A()

def _setup(tmp_path):
    pol = tmp_path/"0_raw"/"policies"; pol.mkdir(parents=True)
    (pol/"d.md").write_text(DOC, encoding="utf-8")
    reg = tmp_path/"themes_registry.yaml"; reg.write_text(REG, encoding="utf-8")
    return str(tmp_path), str(reg)

P1 = '{"themes":["power_market"],"primary_theme":"power_market","comprehensive":true,"scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5}}'
P1_V2G_ALIAS = '{"themes":["v2g_theme"],"primary_theme":"v2g_theme","comprehensive":false,"scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5}}'
P1_ZERO = '{"themes":[],"primary_theme":"","comprehensive":false,"scores":{"D1":1,"D2":1,"D3":1,"D4":1,"D5":1,"D6":1}}'
P2 = '{"影响分析":{"加油":"a","充电":"b","电力_储能_V2G_交易":"c"},"行动建议":["A 趁早:x"],"didi_impact_one_liner":"y"}'

def test_plan_clean_goes_to_write(tmp_path):
    vault, reg = _setup(tmp_path)
    gen_client = LLMClient(client=_seq_fake([P1, P2]), log_path=str(tmp_path/"g.jsonl"))
    judge_client = LLMClient(client=_seq_fake(['{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}']),
                             log_path=str(tmp_path/"j.jsonl"))
    to_write, queue = plan(vault, reg, scoring_text="(略)", gen_client=gen_client, judge_client=judge_client)
    assert len(to_write) == 1 and len(queue) == 0
    rec, draft = to_write[0]
    assert draft.primary_theme == "power_market"
    assert draft.comprehensive is True
    assert draft.importance == 4 and draft.gate_passed_deep is True
    assert set(draft.影响分析.keys()) == {"加油","充电","电力_储能_V2G_交易"}

def test_plan_judge_reject_goes_to_queue(tmp_path):
    vault, reg = _setup(tmp_path)
    gen_client = LLMClient(client=_seq_fake([P1, P2]), log_path=str(tmp_path/"g.jsonl"))
    judge_client = LLMClient(client=_seq_fake(['{"verdict":"reject","dim":"theme","reason":"漏挂","confidence":0.6}']),
                             log_path=str(tmp_path/"j.jsonl"))
    to_write, queue = plan(vault, reg, scoring_text="(略)", gen_client=gen_client, judge_client=judge_client)
    assert len(to_write) == 0 and len(queue) == 1
    assert queue[0].stage == "judge_reject"


def test_plan_reports_each_item_as_it_finishes(tmp_path):
    vault, reg = _setup(tmp_path)
    pol = tmp_path/"0_raw"/"policies"
    (pol/"other.md").write_text(DOC.replace("P_T1", "P_SKIP"), encoding="utf-8")
    gen_client = LLMClient(client=_seq_fake([P1, P2, P1, P2]), log_path=str(tmp_path/"g.jsonl"))
    judge_client = LLMClient(client=_seq_fake([
        '{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}',
        '{"verdict":"reject","dim":"theme","reason":"漏挂","confidence":0.6}',
    ]), log_path=str(tmp_path/"j.jsonl"))
    events = []
    plan(vault, reg, scoring_text="(略)", gen_client=gen_client,
         judge_client=judge_client, on_item=events.append)
    assert [(kind, item.pid) for kind, item in events] == [
        ("draft", "P_T1"),
        ("queue", "P_SKIP"),
    ]


def test_dryrun_item_writer_flushes_jsonl(tmp_path):
    from scripts.l2_themescore.models import BusinessViewDraft, QueueRecord, Scores
    from scripts.l2_themescore.run_2b import _dryrun_item_writer
    writer = _dryrun_item_writer(str(tmp_path))
    draft = BusinessViewDraft(pid="P_OK", themes=["power_market"], primary_theme="power_market",
                              scores=Scores(5, 4, 4, 4, 4, 5), importance=4,
                              gate_passed_deep=True)
    writer(("draft", draft))
    writer(("queue", QueueRecord(pid="P_BAD", stage="program_gate", reason="bad")))
    assert (tmp_path/"proposed_changes"/"drafts.jsonl").read_text(encoding="utf-8").count("\n") == 1
    full = yaml.safe_load((tmp_path/"proposed_changes"/"drafts_full.jsonl").read_text(encoding="utf-8"))
    assert full["pid"] == "P_OK"
    assert full["scores"] == {"D1": 5, "D2": 4, "D3": 4, "D4": 4, "D5": 4, "D6": 5}
    assert full["primary_theme"] == "power_market"
    assert (tmp_path/"review_queue"/"queue.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_loads_drafts_from_full_jsonl(tmp_path):
    from scripts.l2_themescore.run_2b import _draft_full_row, load_drafts_full
    from scripts.l2_themescore.models import BusinessViewDraft, Scores
    draft = BusinessViewDraft(pid="P_OK", themes=["power_market"], primary_theme="power_market",
                              scores=Scores(5, 4, 4, 4, 4, 5), importance=4,
                              action_class="A", value_tags=["机会"], gate_passed_deep=True,
                              comprehensive=True,
                              影响分析={"加油":"a","充电":"b","电力_储能_V2G_交易":"c"},
                              行动建议=["A 趁早:x"], didi_impact_one_liner="y")
    out = tmp_path/"proposed_changes"; out.mkdir()
    (out/"drafts_full.jsonl").write_text(json.dumps(_draft_full_row(draft), ensure_ascii=False) + "\n",
                                         encoding="utf-8")
    loaded = load_drafts_full(str(tmp_path))
    assert len(loaded) == 1
    assert loaded[0].pid == "P_OK"
    assert loaded[0].scores.to_dict() == {"D1": 5, "D2": 4, "D3": 4, "D4": 4, "D5": 4, "D6": 5}
    assert loaded[0].影响分析["充电"] == "b"


def test_load_preview_drafts_falls_back_to_summary_jsonl(tmp_path):
    from scripts.l2_themescore.run_2b import load_preview_drafts
    out = tmp_path/"proposed_changes"; out.mkdir()
    (out/"drafts.jsonl").write_text(json.dumps({
        "pid": "P_OK", "themes": ["power_market"], "primary": "power_market",
        "重要性": 4, "gate": True,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    drafts, full_available = load_preview_drafts(str(tmp_path))
    assert full_available is False
    assert drafts[0].pid == "P_OK"
    assert drafts[0].primary_theme == "power_market"


def test_render_apply_preview_html(tmp_path):
    from scripts.l2_themescore.models import BusinessViewDraft, QueueRecord, Scores
    from scripts.l2_themescore.run_2b import render_apply_preview
    draft = BusinessViewDraft(pid="P_OK", themes=["power_market"], primary_theme="power_market",
                              scores=Scores(5, 4, 4, 4, 4, 5), importance=4,
                              gate_passed_deep=True)
    out = render_apply_preview([draft], [QueueRecord(pid="P_BAD", stage="judge_reject", reason="漏挂")],
                               str(tmp_path/"preview.html"))
    html = (tmp_path/"preview.html").read_text(encoding="utf-8")
    assert out.endswith("preview.html")
    assert "离线 apply 预览" in html
    assert "P_OK" in html and "P_BAD" in html
    assert "不会调用模型" in html


def test_apply_accepted_drafts_writes_from_full_without_models(tmp_path):
    from scripts.l2_themescore.models import BusinessViewDraft, Scores
    from scripts.l2_themescore.run_2b import apply_accepted_drafts
    vault, _ = _setup(tmp_path)
    draft = BusinessViewDraft(pid="P_T1", themes=["power_market"], primary_theme="power_market",
                              scores=Scores(5, 4, 4, 4, 4, 5), importance=4,
                              action_class="A", value_tags=["机会"], gate_passed_deep=True,
                              影响分析={"加油":"a","充电":"b","电力_储能_V2G_交易":"c"},
                              行动建议=["A 趁早:x"])
    written = apply_accepted_drafts(vault, [draft], extracted_at="2026-06-02",
                                    extracted_model="MiniMax-M2.7")
    assert len(written) == 1
    data = yaml.safe_load(Path(written[0]).read_text(encoding="utf-8"))
    assert data["pid"] == "P_T1"
    assert data["extracted_model"] == "MiniMax-M2.7"
    assert data["sanitized_from"].startswith("0_raw/policies/")


def test_apply_accepted_drafts_verifies_only_selected_drafts(tmp_path):
    from scripts.l2_themescore.models import BusinessViewDraft, Scores
    from scripts.l2_themescore.run_2b import apply_accepted_drafts, verify_artifacts
    vault, reg = _setup(tmp_path)
    bv = tmp_path/"_meta"/"business_view"; bv.mkdir(parents=True)
    (bv/"P_OLD_BAD.yaml").write_text(yaml.dump({
        "pid":"P_OLD_BAD","themes":[],"primary_theme":"",
        "scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5},"重要性":1,
        "行动分类":"C","价值标签":[],"gate_passed_deep":False}, allow_unicode=True), encoding="utf-8")
    assert verify_artifacts(vault, reg)
    draft = BusinessViewDraft(pid="P_T1", themes=["power_market"], primary_theme="power_market",
                              scores=Scores(5, 4, 4, 4, 4, 5), importance=4,
                              action_class="A", value_tags=["机会"], gate_passed_deep=True,
                              影响分析={"加油":"a","充电":"b","电力_储能_V2G_交易":"c"},
                              行动建议=["A 趁早:x"])
    written = apply_accepted_drafts(vault, [draft], extracted_at="2026-06-02",
                                    extracted_model="MiniMax-M2.7", registry_path=reg)
    assert len(written) == 1


def test_plan_can_limit_to_include_pids(tmp_path):
    vault, reg = _setup(tmp_path)
    pol = tmp_path/"0_raw"/"policies"
    (pol/"other.md").write_text(DOC.replace("P_T1", "P_SKIP"), encoding="utf-8")
    gen_client = LLMClient(client=_seq_fake([P1, P2]), log_path=str(tmp_path/"g.jsonl"))
    judge_client = LLMClient(client=_seq_fake(['{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}']),
                             log_path=str(tmp_path/"j.jsonl"))
    to_write, queue = plan(vault, reg, scoring_text="(略)", gen_client=gen_client,
                           judge_client=judge_client, include_pids={"P_T1"})
    assert [rec.pid for rec, _ in to_write] == ["P_T1"]
    assert queue == []


def test_plan_canonicalizes_theme_id_suffix_alias(tmp_path):
    vault, reg = _setup(tmp_path)
    gen_client = LLMClient(client=_seq_fake([P1_V2G_ALIAS, P2]), log_path=str(tmp_path/"g.jsonl"))
    judge_client = LLMClient(client=_seq_fake(['{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}']),
                             log_path=str(tmp_path/"j.jsonl"))
    to_write, queue = plan(vault, reg, scoring_text="(略)", gen_client=gen_client,
                           judge_client=judge_client)
    assert queue == []
    assert to_write[0][1].themes == ["v2g"]
    assert to_write[0][1].primary_theme == "v2g"


def test_plan_allows_zero_theme_without_deep_generation(tmp_path):
    vault, reg = _setup(tmp_path)
    gen_client = LLMClient(client=_seq_fake([P1_ZERO]), log_path=str(tmp_path/"g.jsonl"))
    judge_client = LLMClient(client=_seq_fake(['{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}']),
                             log_path=str(tmp_path/"j.jsonl"))
    to_write, queue = plan(vault, reg, scoring_text="(略)", gen_client=gen_client,
                           judge_client=judge_client)
    assert queue == []
    assert len(to_write) == 1
    assert to_write[0][1].themes == []
    assert to_write[0][1].primary_theme == ""
    assert to_write[0][1].gate_passed_deep is False
    assert to_write[0][1].影响分析 is None


def test_evidence_normalizer_drops_unsupported_equipment_and_residential_themes():
    from scripts.l2_themescore.models import BusinessViewDraft, Scores
    from scripts.l2_themescore.run_2b import _normalize_theme_evidence
    rec = type("R", (), {
        "body_head": "新能源汽车规划提出完善充换电基础设施,推动汽车向储能单元转变。",
    })()
    draft = BusinessViewDraft(
        pid="P",
        themes=["charging_infra", "v2g", "residential_charging", "equipment_renewal_theme"],
        primary_theme="charging_infra",
        scores=Scores(4, 3, 4, 2, 3, 4),
    )

    _normalize_theme_evidence(rec, draft)

    assert draft.themes == ["charging_infra", "v2g"]
    assert draft.primary_theme == "charging_infra"


def test_evidence_normalizer_drops_conceptual_storage_unit_theme():
    from scripts.l2_themescore.models import BusinessViewDraft, Scores
    from scripts.l2_themescore.run_2b import _normalize_theme_evidence
    rec = type("R", (), {
        "body_head": "新能源汽车规划提出汽车向移动智能终端、储能单元转变,并完善充换电基础设施。",
    })()
    draft = BusinessViewDraft(
        pid="P",
        themes=["charging_infra", "v2g", "energy_storage_theme"],
        primary_theme="charging_infra",
        scores=Scores(4, 3, 4, 2, 3, 4),
    )

    _normalize_theme_evidence(rec, draft)

    assert draft.themes == ["charging_infra", "v2g"]


def test_evidence_normalizer_keeps_direct_storage_project_theme():
    from scripts.l2_themescore.models import BusinessViewDraft, Scores
    from scripts.l2_themescore.run_2b import _normalize_theme_evidence
    rec = type("R", (), {
        "body_head": "支持新型储能项目常态化参与电力现货市场交易,建设用户侧储能设施。",
    })()
    draft = BusinessViewDraft(
        pid="P",
        themes=["energy_storage_theme", "power_market"],
        primary_theme="energy_storage_theme",
        scores=Scores(5, 4, 4, 4, 4, 4),
    )

    _normalize_theme_evidence(rec, draft)

    assert "energy_storage_theme" in draft.themes


def test_evidence_normalizer_prioritizes_charging_primary_when_buildout_is_explicit():
    from scripts.l2_themescore.models import BusinessViewDraft, Scores
    from scripts.l2_themescore.run_2b import _normalize_theme_evidence
    rec = type("R", (), {
        "body_head": "推进电动汽车充电基础设施建设,实现加油站充电设施全覆盖,在居民小区推进停车位电气化改造。",
    })()
    draft = BusinessViewDraft(
        pid="P",
        themes=["distribution_grid_opening", "charging_infra", "residential_charging"],
        primary_theme="distribution_grid_opening",
        scores=Scores(4, 4, 3, 4, 4, 2),
    )

    _normalize_theme_evidence(rec, draft)

    assert draft.themes == ["distribution_grid_opening", "charging_infra", "residential_charging"]
    assert draft.primary_theme == "charging_infra"


def test_normalizes_pass2_fields_nested_in_impact():
    from scripts.l2_themescore.run_2b import _normalize_pass2_payload
    impact, actions, one_liner = _normalize_pass2_payload({
        "影响分析": {
            "加油": "a",
            "充电": "b",
            "电力_储能_V2G_交易": "c",
            "行动建议": ["A 趁早:x"],
            "didi_impact_one_liner": "one",
        }
    })
    assert set(impact.keys()) == {"加油", "充电", "电力_储能_V2G_交易"}
    assert actions == ["A 趁早:x"]
    assert one_liner == "one"


def test_verify_artifacts_catches_tampered(tmp_path):
    from scripts.l2_themescore.run_2b import verify_artifacts
    bv = tmp_path/"_meta"/"business_view"; bv.mkdir(parents=True)
    reg = tmp_path/"themes_registry.yaml"; reg.write_text(REG, encoding="utf-8")
    (bv/"P_OK.yaml").write_text(yaml.dump({
        "pid":"P_OK","themes":["power_market"],"primary_theme":"power_market",
        "scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5},"重要性":4,"行动分类":"A",
        "价值标签":["机会"],"影响分析":{"加油":"a","充电":"b","电力_储能_V2G_交易":"c"},
        "行动建议":["A 趁早:x"],"gate_passed_deep":True}, allow_unicode=True), encoding="utf-8")
    (bv/"P_BAD.yaml").write_text(yaml.dump({
        "pid":"P_BAD","themes":["power_market"],"primary_theme":"power_market",
        "scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5},"重要性":1,"行动分类":"A",
        "价值标签":["机会"],"gate_passed_deep":False}, allow_unicode=True), encoding="utf-8")
    failures = verify_artifacts(str(tmp_path), str(reg))
    bad = [pid for pid, _ in failures]
    assert "P_BAD" in bad and "P_OK" not in bad


def test_make_client_picks_provider(tmp_path):
    from scripts.l2_themescore.run_2b import make_client
    from scripts.common.llm import LLMClient, OpenAICompatClient
    log = str(tmp_path / "c.jsonl")
    assert isinstance(make_client("anthropic", "claude-x", log), LLMClient)
    assert isinstance(make_client("openai", "qwen3.6-plus", log), OpenAICompatClient)
