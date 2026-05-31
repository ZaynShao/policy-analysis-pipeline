from scripts.l2_themescore.models import Scores, BusinessViewDraft, JudgeVerdict

def test_scores_roundtrip():
    s = Scores(D1=5, D2=4, D3=4, D4=4, D5=3, D6=5)
    assert s.to_dict() == {"D1":5,"D2":4,"D3":4,"D4":4,"D5":3,"D6":5}
    assert Scores.from_dict({"D1":5,"D2":4,"D3":4,"D4":4,"D5":3,"D6":5}) == s

def test_draft_minimal():
    d = BusinessViewDraft(pid="P_X", themes=["power_market"], primary_theme="power_market",
                          scores=Scores(3,3,3,3,3,3))
    assert d.pid == "P_X"
    assert d.importance is None
    assert d.影响分析 is None and d.行动建议 == []

def test_verdict_fields():
    v = JudgeVerdict(verdict="reject", dim="theme", reason="漏挂储能", confidence=0.8)
    assert v.verdict == "reject"
