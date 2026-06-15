"""Tests for news_filter."""
from __future__ import annotations
from scripts.l1_collect.news_filter import is_news_or_press


def test_blocked_domain_media():
    assert is_news_or_press(
        url="https://www.xinhuanet.com/article/x", title="某政策解读", issuer="",
    ).is_filtered is True


def test_blocked_domain_storage_network():
    assert is_news_or_press(
        url="https://www.escn.com.cn/news/x.html", title="湖南储能项目推进", issuer="",
    ).is_filtered is True


def test_title_suffix_market_county():
    assert is_news_or_press(
        url="https://example.gov.cn/x", title="信阳新能源发展看区域转型_市县",
        issuer="信阳市政府",
    ).is_filtered is True


def test_gov_policy_page_pass():
    """政府网政策原文应通过(issuer 是政府机关)。"""
    r = is_news_or_press(
        url="https://www.gov.cn/zhengce/2024/x.html",
        title="国务院关于xxx的通知", issuer="国务院",
    )
    assert r.is_filtered is False


def test_no_issuer_lookup_fail_non_gov():
    """issuer 缺失 且非政府域名 → 过滤。"""
    r = is_news_or_press(
        url="https://unknown.cn/x", title="某通知", issuer=None,
    )
    assert r.is_filtered is True
    assert "issuer_unknown" in r.reasons


def test_no_issuer_but_gov_domain_pass_to_step45():
    """政府域名但 issuer 缺失 → 进 step4.5 二次过滤,Step 3 放过。"""
    r = is_news_or_press(
        url="https://fgw.beijing.gov.cn/x", title="关于xx的通知", issuer=None,
    )
    # 这条只有 issuer_unknown_but_gov_domain reason,但 is_filtered 还是 True
    # 由 step3_filter 区分:if reasons == ["issuer_unknown_but_gov_domain"] 则放行
    assert "issuer_unknown_but_gov_domain" in r.reasons


# ---------------------------------------------------------------------------
# 非政策标题/类型黑名单(市监 backfill 污染:采购公告 / 党建活动 / 列表页行)
# gov 域名 + gov issuer 时旧逻辑一律放行,这些确定性非政策类型须被拦下。
# ---------------------------------------------------------------------------

def test_procurement_title_filtered():
    """采购中标公告(政府域名 + 政府 issuer)应被过滤,不当政策。"""
    r = is_news_or_press(
        url="https://amr.hainan.gov.cn/xxgk/x.html",
        title="海南省市场监督管理局公平竞争审查咨询服务采购项目中标公告",
        issuer="海南省市场监督管理局",
    )
    assert r.is_filtered is True
    assert any(x.startswith("non_policy_title") for x in r.reasons)


def test_party_campaign_title_filtered():
    """党建活动新闻(大学习大讨论大提升)应被过滤。"""
    r = is_news_or_press(
        url="https://scjgj.nc.gov.cn/news/x.html",
        title="南昌市市场监管局开展大学习大讨论大提升活动",
        issuer="南昌市市场监督管理局",
    )
    assert r.is_filtered is True
    assert any(x.startswith("non_policy_title") for x in r.reasons)


def test_list_row_box_drawing_filtered():
    """列表页/侧边栏行(含框线符)应被过滤。"""
    r = is_news_or_press(
        url="https://scjgj.beijing.gov.cn/zwxx/x.html",
        title="├网络交易和合同监管",
        issuer="北京市市场监督管理局",
    )
    assert r.is_filtered is True
    assert "non_policy_list_row" in r.reasons


def test_report_release_artifact_filtered():
    """报告发布通告(发布《...年度报告(2025)》):报告作为带书名号/年份的成果物,应过滤。"""
    r = is_news_or_press(
        url="https://samr.gov.cn/xw/x.html",
        title="市场监管总局发布《中国反垄断执法年度报告(2025)》",
        issuer="国家市场监督管理总局",
    )
    assert r.is_filtered is True
    assert any(x.startswith("non_policy_title") for x in r.reasons)


def test_real_policy_annual_report_rule_not_filtered():
    """精度护栏:含'年度报告'但是真政策(《企业年度报告公示办法》)不能误杀。"""
    r = is_news_or_press(
        url="https://samr.gov.cn/zcfg/x.html",
        title="市场监督管理总局关于印发《企业年度报告公示办法》的通知",
        issuer="国家市场监督管理总局",
    )
    assert r.is_filtered is False


def test_real_policy_report_submission_rule_not_filtered():
    """精度护栏:'发布...年度报告的通知'(报送制度类政策),报告后非成果物收束,不误杀。"""
    r = is_news_or_press(
        url="https://samr.gov.cn/zcfg/x.html",
        title="关于做好2025年度报告报送工作的通知",
        issuer="国家市场监督管理总局",
    )
    assert r.is_filtered is False


def test_nel_title_not_treated_as_list_row():
    """精度护栏:U+0085(NEL)等控制符不是框线符,真政策不能被结构规则误杀。"""
    r = is_news_or_press(
        url="https://www.gov.cn/zhengce/x.html",
        title="关于新能源\x85汽车补贴的通知",
        issuer="国务院",
    )
    assert r.is_filtered is False
