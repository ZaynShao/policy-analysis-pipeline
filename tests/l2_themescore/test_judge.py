from scripts.common.llm import LLMClient
from scripts.l2_themescore.models import Scores, BusinessViewDraft
from scripts.l2_themescore.judge import JUDGE_SYSTEM, judge_draft
from scripts._oneshot.calibrate_judge_2b import CALIBRATION_JUDGE_SYSTEM

def _fake(payload):
    class M:
        def create(self, **kw):
            class R: content=[type("B",(),{"text":payload})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages=M()
    return A()

def _d(): return BusinessViewDraft(pid="P", themes=["power_market"], primary_theme="power_market",
                                   scores=Scores(5,4,4,4,4,5), importance=4, action_class="A")

def test_judge_accept(tmp_path):
    c = LLMClient(client=_fake('{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}'),
                  log_path=str(tmp_path/"l.jsonl"))
    v = judge_draft(c, rec_title="某电力市场政策", rec_body="...", draft=_d())
    assert v.verdict == "accept" and v.confidence == 0.9

def test_judge_reject(tmp_path):
    c = LLMClient(client=_fake('{"verdict":"reject","dim":"theme","reason":"漏挂储能","confidence":0.7}'),
                  log_path=str(tmp_path/"l.jsonl"))
    v = judge_draft(c, rec_title="储能政策", rec_body="...", draft=_d())
    assert v.verdict == "reject" and v.dim == "theme"

def test_judge_has_reasoning_headroom(tmp_path):
    # judge 可能是 reasoning 模型(DeepSeek/Qwen 等),预算太小会被思考耗光→content 为空。
    seen = []
    class M:
        def create(self, **kw):
            seen.append(kw.get("max_tokens"))
            class R: content=[type("B",(),{"text":'{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}'})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages=M()
    c = LLMClient(client=A(), log_path=str(tmp_path/"l.jsonl"))
    judge_draft(c, rec_title="t", rec_body="b", draft=_d())
    assert seen[0] >= 2048

def test_judge_includes_evidence_beyond_body_head(tmp_path):
    seen = []
    class M:
        def create(self, **kw):
            seen.append(kw["messages"][0]["content"])
            class R: content=[type("B",(),{"text":'{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}'})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages=M()
    c = LLMClient(client=A(), log_path=str(tmp_path/"l.jsonl"))
    marker = "MARKER_AFTER_1500"
    judge_draft(c, rec_title="t", rec_body=("x" * 1700) + marker, draft=_d())
    assert marker in seen[0]

def test_calibration_judge_prompt_preserves_business_theme_boundary():
    assert "13 个滴滴业务主题" in CALIBRATION_JUDGE_SYSTEM
    assert "不得发明" in CALIBRATION_JUDGE_SYSTEM
    assert "零主题" in CALIBRATION_JUDGE_SYSTEM
    assert "边界争议默认 accept" in CALIBRATION_JUDGE_SYSTEM

def test_production_judge_prompt_uses_hardened_boundary():
    assert "13 个滴滴业务主题" in JUDGE_SYSTEM
    assert "不得发明" in JUDGE_SYSTEM
    assert "零主题" in JUDGE_SYSTEM
    assert "边界争议默认 accept" in JUDGE_SYSTEM
    assert "标准制定" in JUDGE_SYSTEM
    assert "不等于直接命中" in JUDGE_SYSTEM
    assert "政府公报目录" in JUDGE_SYSTEM
    assert "任一主题" in JUDGE_SYSTEM
    assert "设备更新/标准提升" in JUDGE_SYSTEM
