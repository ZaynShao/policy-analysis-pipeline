"""Tests for cn_dates: 中文数字日期解析 + 发文日(落款)语义优先选取。

这是 date 抽取的单一真相源:既识别中文数字落款(二〇二三年九月),又按上下文
剔除生效/截止日,只留发文/落款日。L1 metadata_extractor 与 L2 extractors 都复用它。
"""
from __future__ import annotations
from scripts.l1_collect.cn_dates import (
    cn_year_to_int, cn_md_to_int, pick_issuance_date, is_effective_or_deadline_date,
)


# ── 中文数字转换 ──────────────────────────────────────────────
def test_cn_year():
    assert cn_year_to_int("二〇二三") == 2023
    assert cn_year_to_int("二〇二六") == 2026
    assert cn_year_to_int("二〇〇九") == 2009


def test_cn_month_day():
    assert cn_md_to_int("一") == 1
    assert cn_md_to_int("九") == 9
    assert cn_md_to_int("十") == 10
    assert cn_md_to_int("十一") == 11
    assert cn_md_to_int("十五") == 15
    assert cn_md_to_int("二十") == 20
    assert cn_md_to_int("二十八") == 28
    assert cn_md_to_int("三十") == 30
    assert cn_md_to_int("三十一") == 31


# ── pick_issuance_date:剔除生效/截止,留落款 ───────────────────
def test_pick_drops_effective_keeps_luokuan():
    text = "本通知自2026年7月1日起执行。\n\n浙江省发展和改革委员会\n2026年5月28日"
    assert pick_issuance_date(text) == "2026-05-28"


def test_pick_returns_empty_when_only_deadline():
    assert pick_issuance_date("本办法有效期至2026年12月31日。") == ""


def test_pick_returns_empty_when_only_effective():
    assert pick_issuance_date("本通知自2025年3月1日起施行。") == ""


def test_pick_chinese_numeral_full():
    assert pick_issuance_date("国家发展和改革委员会\n二〇二三年九月十五日") == "2023-09-15"


def test_pick_chinese_numeral_month_only_defaults_day_01():
    assert pick_issuance_date("国家发展和改革委员会\n二〇二三年九月") == "2023-09-01"


def test_pick_prefers_last_neutral_date():
    # 多个中性日期 → 取最末(落款在文末)
    text = "2026年1月5日发布征求意见稿。……\n\n浙江省发展和改革委员会\n2026年5月28日"
    assert pick_issuance_date(text) == "2026-05-28"


# ── is_effective_or_deadline_date:resolver 用来判定存量误标 ────
def test_is_effective_true_for_effective_date():
    text = "本通知自2026年7月1日起执行。\n浙江省发展和改革委员会\n2026年5月28日"
    assert is_effective_or_deadline_date(text, "2026-07-01") is True
    assert is_effective_or_deadline_date(text, "2026-05-28") is False


def test_is_deadline_true_for_deadline_date():
    text = "本办法有效期至2026年12月31日。"
    assert is_effective_or_deadline_date(text, "2026-12-31") is True


def test_is_effective_false_for_absent_date():
    text = "落款 2016年3月17日"
    assert is_effective_or_deadline_date(text, "2024-05-01") is False
