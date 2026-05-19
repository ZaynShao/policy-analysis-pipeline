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
