"""Tests for cn_dates: 中文数字日期解析 + 发文日(落款)语义优先选取。

这是 date 抽取的单一真相源:既识别中文数字落款(二〇二三年九月),又按上下文
剔除生效/截止日,只留发文/落款日。L1 metadata_extractor 与 L2 extractors 都复用它。
"""
from __future__ import annotations
from scripts.l1_collect.cn_dates import (
    cn_year_to_int, cn_md_to_int, pick_issuance_date, is_effective_or_deadline_date,
    appears_as_issuance, pick_luokuan_strict,
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


# ── 真实 vault 失败模式回归 ─────────────────────────────────
def test_pick_excludes_scrape_footer():
    # trafilatura 采集页脚 `_采集于 YYYY-MM-DD` 不是落款,必须剔除
    text = ("上海市发展和改革委员会\n二○一二年六月十五日\n\n"
            "打印本页关闭窗口\n\n---\n\n_采集于 2026-04-25T11:07:53.123")
    assert pick_issuance_date(text) == "2012-06-15"


def test_x_qian_is_deadline_not_issuance():
    # "YYYY年MM月DD日前" = 任务截止,不是发文日
    text = "2026年12月31日前，重点碳排放单位应报送。\n北京市生态环境局\n2026年3月18日"
    assert is_effective_or_deadline_date(text, "2026-12-31") is True
    assert pick_issuance_date(text) == "2026-03-18"


def test_appears_as_issuance():
    # 同一日期既出现在生效句又出现在落款 → 算 issuance(发文日==生效日,常见)
    text = "本实施细则自2024年9月27日起施行。\n上海市公安局\n2024年9月27日"
    assert appears_as_issuance(text, "2024-09-27") is True
    assert appears_as_issuance(text, "2024-09-28") is False


# ── pick_luokuan_strict:高置信落款(回填覆盖存量用)─────────────
def test_strict_accepts_org_adjacent():
    assert pick_luokuan_strict("重庆市发展和改革委员会\n2022年6月1日") == "2022-06-01"


def test_strict_accepts_chinese_numeral():
    assert pick_luokuan_strict("国家发展改革委 国家能源局\n二〇二三年九月") == "2023-09-01"


def test_strict_accepts_publish_label():
    assert pick_luokuan_strict("## 政策原文\n\n日期：2024-08-29 来源：北京市") == "2024-08-29"


def test_strict_rejects_interaction_timestamp():
    # 咨询互动表格的"回复时间/提交时间"不是落款 → 不采信
    text = "| 提交时间 | 2025-11-09 |\n| 回复时间 | 2025-11-13 |"
    assert pick_luokuan_strict(text) == ""


def test_strict_rejects_eligibility_range_date():
    # 申报条件里的范围日期,无机关/标签背书 → 不采信
    text = "购买日期应介于2024年1月1日至2024年12月31日之间。"
    assert pick_luokuan_strict(text) == ""
