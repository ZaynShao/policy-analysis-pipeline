"""Tests for dedup: URL / 文号 / 标题 三维查重。"""
from __future__ import annotations
from scripts.l1_collect.dedup import (
    normalize_url, normalize_official_number, normalize_title, DedupIndex,
)


def test_normalize_url_strips_fragment_query_trailing_slash():
    # tracking 参数(utm_source)和 fragment 应被剥除,末尾斜杠归一
    assert normalize_url("https://x.gov.cn/a/?utm_source=wx#sec") == normalize_url("https://x.gov.cn/a")


def test_normalize_official_number_removes_brackets():
    a = normalize_official_number("发改能源〔2024〕1128号")
    b = normalize_official_number("发改能源[2024]1128号")
    c = normalize_official_number("发改能源(2024)1128号")
    assert a == b == c


def test_normalize_title_drops_punct_whitespace():
    assert normalize_title("关于xx的 通知(2024 年版)") == normalize_title("关于xx的通知2024年版")


def test_dedup_index_url_hit():
    idx = DedupIndex()
    idx.add(url="https://x.gov.cn/a", official_number="", title="通知 1")
    assert idx.is_dup(url="https://x.gov.cn/a/?utm_source=z", official_number="", title="完全不同的标题")


def test_dedup_index_official_number_hit():
    idx = DedupIndex()
    idx.add(url="https://x.gov.cn/a", official_number="发改能源〔2024〕1128号", title="通知 1")
    assert idx.is_dup(url="https://y.gov.cn/b", official_number="发改能源[2024]1128号", title="不同")


def test_dedup_index_title_hit():
    idx = DedupIndex()
    idx.add(url="https://x.gov.cn/a", official_number="", title="关于xx的通知 (2024)")
    assert idx.is_dup(url="https://y.gov.cn/b", official_number="", title="关于xx的通知2024")


def test_dedup_index_no_collision_for_distinct():
    idx = DedupIndex()
    idx.add(url="https://x.gov.cn/a", official_number="〔2024〕1号", title="通知 A")
    assert not idx.is_dup(url="https://y.gov.cn/b", official_number="〔2024〕2号", title="通知 B")


def test_normalize_url_keeps_identifying_query():
    a = normalize_url("https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=20581")
    b = normalize_url("https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=20272")
    assert a != b                       # 不同 id → 不同 doc,绝不可塌成一个


def test_normalize_url_strips_tracking_and_fragment():
    a = normalize_url("https://x.gov.cn/a/b?id=5&utm_source=wx#sec")
    b = normalize_url("https://x.gov.cn/a/b?id=5")
    assert a == b                       # tracking + fragment 不影响身份


def test_normalize_url_trailing_slash_and_case():
    assert normalize_url("HTTPS://X.GOV.CN/a/") == normalize_url("https://x.gov.cn/a")
