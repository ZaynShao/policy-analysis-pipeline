import yaml
from scripts.common.llm import LLMClient
from scripts.l2_themescore.run_2b import plan

REG = """schema_version: 1.0
themes:
  - {id: power_market, zh: 电力市场, aliases: [电力市场, 现货交易]}
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

P1 = '{"themes":["power_market"],"primary_theme":"power_market","scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5}}'
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
