from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.dedup_group import group_duplicates


def _rec(pid, url, offnum, title, date):
    return PolicyRecord(pid=pid, path=f"/{pid}.md", title=title, official_number=offnum,
        date=date, issuer=[], issuer_canonical=[], url=url, body_head="", raw_fm={})


def test_groups_by_any_dimension_and_keeps_earliest():
    recs = [
        _rec("P_A", "https://x.gov.cn/a/", "发改〔2024〕1号", "标题甲", "2024-01-01"),
        _rec("P_B", "https://x.gov.cn/a",  "发改〔2024〕1号", "标题甲(转)", "2024-02-01"),  # 同URL/同文号
        _rec("P_C", "https://y.gov.cn/z",  "", "完全不同的政策", "2024-03-01"),            # 独立
    ]
    findings = group_duplicates(recs)
    assert len(findings) == 1                 # 一个重复组
    f = findings[0]
    assert f.detail["keep"] == "P_A"          # 最早
    assert set(f.detail["dups"]) == {"P_B"}
