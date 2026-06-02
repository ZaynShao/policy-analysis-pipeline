import json
from scripts.common.llm import LLMClient
from scripts.l2_themescore.generator import parse_json_block, gen_pass1, gen_pass2
from scripts.l2_themescore.prompts import pass1_system, pass2_system

def _fake(payload):
    class M:
        def create(self, **kw):
            class R: content = [type("B",(),{"text": payload})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages = M()
    return A()

def _seq_fake(payloads):
    state = {"i": 0}
    class M:
        def create(self, **kw):
            payload = payloads[min(state["i"], len(payloads)-1)]
            state["i"] += 1
            class R: content = [type("B",(),{"text": payload})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages = M()
    return A()

def test_parse_json_block_strips_fence():
    assert parse_json_block('```json\n{"a":1}\n```') == {"a":1}
    assert parse_json_block('{"b":2}') == {"b":2}

def test_gen_pass1(tmp_path):
    payload = '{"themes":["power_market"],"primary_theme":"power_market","scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5}}'
    c = LLMClient(client=_fake(payload), log_path=str(tmp_path/"l.jsonl"))
    out = gen_pass1(c, system="sys", user="u")
    assert out["primary_theme"] == "power_market"
    assert out["scores"]["D1"] == 5

def test_gen_pass2(tmp_path):
    payload = '{"影响分析":{"加油":"a","充电":"b","电力_储能_V2G_交易":"c"},"行动建议":["A 趁早:x"],"didi_impact_one_liner":"y"}'
    c = LLMClient(client=_fake(payload), log_path=str(tmp_path/"l.jsonl"))
    out = gen_pass2(c, system="sys", user="u")
    assert set(out["影响分析"].keys()) == {"加油","充电","电力_储能_V2G_交易"}

def test_gen_repairs_json_after_strict_retry_fails(tmp_path):
    c = LLMClient(client=_seq_fake(['{"a":', '{"a":', '{"a":1}']), log_path=str(tmp_path/"l.jsonl"))
    out = gen_pass1(c, system="sys", user="u")
    assert out == {"a": 1}

def test_pass1_prompt_blocks_standard_weak_mention_overhang():
    class R:
        ids = ["equipment_renewal_theme", "energy_storage_theme", "vpp_theme", "charging_infra"]
        zh = {x: x for x in ids}
        aliases = {x: [] for x in ids}
    prompt = pass1_system(R(), scoring_text="scores")
    assert "标准制定" in prompt
    assert "不等于 theme 命中" in prompt
    assert "不得因清单式提到" in prompt
    assert "政府公报目录" in prompt
    assert "应归零主题" in prompt

def test_pass1_prompt_prioritizes_explicit_charging_buildout_over_grid_context():
    class R:
        ids = ["distribution_grid_opening", "charging_infra", "residential_charging"]
        zh = {x: x for x in ids}
        aliases = {x: [] for x in ids}
    prompt = pass1_system(R(), scoring_text="scores")
    assert "充电设施全覆盖" in prompt
    assert "停车位电气化改造" in prompt
    assert "primary_theme 应优先选 charging_infra" in prompt
    assert "residential_charging" in prompt

def test_pass1_prompt_blocks_macro_nev_over_expansion():
    class R:
        ids = ["charging_infra", "v2g", "vpp_theme", "green_power_trading_theme",
               "energy_storage_theme", "equipment_renewal_theme"]
        zh = {x: x for x in ids}
        aliases = {x: [] for x in ids}
    prompt = pass1_system(R(), scoring_text="scores")
    assert "新能源汽车宏观规划" in prompt
    assert "储能单元" in prompt
    assert "不得自动挂 energy_storage_theme" in prompt
    assert "不得自动挂 equipment_renewal_theme" in prompt

def test_pass2_prompt_blocks_impact_hallucination():
    prompt = pass2_system()
    assert "不得编造" in prompt
    assert "正文明确" in prompt
    assert "未直接涉及" in prompt
    assert "V2G" in prompt and "虚拟电厂" in prompt
    assert "量化指标" in prompt
    assert "标准制定" in prompt
    assert "不等于直接业务影响" in prompt

def _capture():
    seen = []
    P = '{"themes":["power_market"],"primary_theme":"power_market","scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5}}'
    class M:
        def create(self, **kw):
            seen.append(kw.get("max_tokens"))
            class R: content = [type("B",(),{"text": P})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages = M()
    return A(), seen

def test_gen_passes_have_reasoning_headroom(tmp_path):
    # reasoning 模型须留足"思考+输出"预算;原 896/1024 偏紧→截断成空。守这条不回退。
    client_obj, seen = _capture()
    c = LLMClient(client=client_obj, log_path=str(tmp_path/"l.jsonl"))
    gen_pass1(c, system="s", user="u")
    gen_pass2(c, system="s", user="u")
    assert seen[0] >= 2048   # pass1
    assert seen[1] >= 2048   # pass2
