from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.news_classifier import classify_corpus


def _rec(pid, title, url, issuer):
    return PolicyRecord(pid=pid, path=f"/x/{pid}.md", title=title,
        official_number="", date="2025-01-01", issuer=[issuer] if issuer else [],
        issuer_canonical=[], url=url, body_head="正文", raw_fm={})


def test_obvious_policy_not_flagged_skips_llm():
    calls = []
    def fake_llm(system, user): calls.append(user); return "{}"
    recs = [_rec("P_2025_NDRC_1", "关于推进虚拟电厂的通知",
                 "https://www.ndrc.gov.cn/x.html", "国家发展和改革委员会")]
    findings = classify_corpus(recs, fake_llm)
    assert findings == []          # heuristic 通过 → 不进 LLM
    assert calls == []


def test_heuristic_flagged_then_llm_confirms_news():
    def fake_llm(system, user):
        return '{"label":"news_release","confidence":0.97,"evidence":"媒体转载"}'
    recs = [_rec("P_2025_X_2", "某新政解读_市县",
                 "https://www.sohu.com/a.html", "搜狐")]
    findings = classify_corpus(recs, fake_llm)
    assert len(findings) == 1
    f = findings[0]
    assert f.check == "news_release"
    assert f.detail["label"] == "news_release"
    assert f.detail["confidence"] == 0.97
    assert "_archive" in f.proposed_action
