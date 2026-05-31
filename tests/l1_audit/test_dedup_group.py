from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.dedup_group import group_duplicates


def _rec(pid, url, offnum, title, date):
    return PolicyRecord(pid=pid, path=f"/{pid}.md", title=title, official_number=offnum,
        date=date, issuer=[], issuer_canonical=[], url=url, body_head="", raw_fm={})


def test_title_match_with_conflicting_offnum_not_merged():
    recs = [
        _rec("P_NDRC_20", "https://x/a", "国家发展改革委令第20号", "电力市场运行基本规则", "2024-04-25"),
        _rec("P_NDRC_15", "https://x/b", "国家发展改革委令第15号", "电力市场运行基本规则", "2024-05-10"),
    ]
    assert group_duplicates(recs) == []   # 同标题但文号冲突 → 不并(版本对)


def test_url_query_distinct_not_merged():
    recs = [
        _rec("P_A", "https://n.gov.cn/iteminfo.jsp?id=20581", "", "电力中长期市场基本规则", "2025-12-17"),
        _rec("P_B", "https://n.gov.cn/iteminfo.jsp?id=20272", "", "电力现货市场基本规则", "2027-01-01"),
    ]
    assert group_duplicates(recs) == []   # 不同 id → 不同 doc → 不并


def test_groups_by_any_dimension_and_keeps_earliest():
    recs = [
        _rec("P_A", "https://x.gov.cn/a/", "发改〔2024〕1号", "标题甲", "2024-01-01"),
        _rec("P_B", "https://x.gov.cn/a",  "发改〔2024〕1号", "标题甲(转)", "2024-02-01"),  # 同URL/同文号
        _rec("P_C", "https://y.gov.cn/z",  "", "完全不同的政策", "2024-03-01"),            # 独立
    ]
    findings = group_duplicates(recs)
    assert len(findings) == 1                 # 一个重复组
    f = findings[0]
    assert f.detail["keep"] == "P_A"          # 文号同档 → date 最早
    assert set(f.detail["dups"]) == {"P_B"}


def test_keep_prefers_record_with_official_number():
    # 真重复(同标题、文号一空一有 → 不冲突可并)。保留带文号者做 canonical,
    # 不能因 date-tie 的 pid 排序把带文号的那条迁走、丢掉 live 语料的文号。
    recs = [
        _rec("P_aaa", "https://beijing.gov.cn/x", "", "新能源汽车产业发展规划", "2020-10-20"),
        _rec("P_zzz", "https://shanghai.gov.cn/y", "国办发〔2020〕39号", "新能源汽车产业发展规划", "2020-10-20"),
    ]
    f = group_duplicates(recs)[0]
    assert f.detail["keep"] == "P_zzz"        # 带文号者优先,即便 pid 排序在后
    assert f.detail["dups"] == ["P_aaa"]
