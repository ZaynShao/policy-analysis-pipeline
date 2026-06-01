import json
from scripts.common.llm import LLMClient
from scripts.l2_themescore.generator import parse_json_block, gen_pass1, gen_pass2

def _fake(payload):
    class M:
        def create(self, **kw):
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
