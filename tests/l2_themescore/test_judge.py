from scripts.common.llm import LLMClient
from scripts.l2_themescore.models import Scores, BusinessViewDraft
from scripts.l2_themescore.judge import judge_draft

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
    # judge 可能是 reasoning 模型(Qwen 等),256 太小→思考耗光预算;守住头寸不回退。
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
    assert seen[0] >= 1024
