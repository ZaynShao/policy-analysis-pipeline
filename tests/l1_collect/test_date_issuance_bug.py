"""复现:L1 date / official_number 抽取系统性根因 bug。

背景:2026-05 能源月刊 L-cov 查漏发现——`date` frontmatter 抓成了
"生效/截止/执行起始日"而非"发文/印发/落款日",导致按月过滤漏掉真实发文于该月的政策。
official_number 还会错抓被废止旧件号。

证据(vault raw,只读):
- P_2026_ZJ_FGW_21:落款 2026年5月28日,却 date='2026-07-01'(误取"自2026年7月1日起执行");
  official_number 误抓 '浙发改价格〔2024〕21号'(被废止旧件号)。
- P_2027_NDRC_572b0ea8:落款"二〇二三年九月"(中文数字),却 date='2027-01-01'、id 桶错成 2027。
- P_2026_BJ_559a203d:date='2026-12-31'(截止日)。

机制层目标:优先取落款/发文/印发日,绝不取生效/截止/执行起始日;识别中文数字落款;
official_number 不取被废止/原件号。这些测试表达"修复后应有的行为",当前应为 RED。
"""
from __future__ import annotations
from scripts.l1_collect.metadata_extractor import extract_official_number, extract_date
from scripts.l2_attribution.extractors import extract_luokuan_date


# ── L1 extract_date:落款日优先于生效/截止日 ──────────────────────────────

def test_date_prefers_luokuan_over_effective_date():
    """P_2026_ZJ_FGW_21:生效句在前、落款在文末 → 必须取落款 5/28,而非生效 7/1。"""
    body = (
        "浙江省发展和改革委员会关于工商业分时电价的通知\n\n"
        "一、……\n二、本通知自2026年7月1日起执行。\n\n"
        "浙江省发展和改革委员会\n2026年5月28日\n"
    )
    assert extract_date("", body=body) == "2026-05-28"


def test_date_never_returns_deadline_date():
    """P_2026_BJ_559a203d:正文只含截止日 → 不得把截止日当 date(宁可空)。"""
    body = "本办法有效期至2026年12月31日。"
    assert extract_date("", body=body) != "2026-12-31"


def test_date_url_publish_still_wins():
    """回归:URL path 发布日仍是最优先来源,不被正文生效句干扰。"""
    url = "https://fgw.zj.gov.cn/art/2026/5/28/art_1_1.html"
    body = "本通知自2026年7月1日起执行。"
    assert extract_date(url, body=body) == "2026-05-28"


# ── L1 extract_official_number:不取被废止/原件号 ────────────────────────

def test_official_number_skips_repealed():
    """P_2026_ZJ_FGW_21:正文仅出现被废止旧件号 → 不得返回它(宁可空)。"""
    body = "原《浙江省分时电价管理办法》(浙发改价格〔2024〕21号)自本通知施行之日起废止。"
    assert extract_official_number(body) != "浙发改价格〔2024〕21号"


def test_official_number_prefers_own_over_repealed():
    """本件文号与被废止件号并存(废止句在前)→ 取本件号,不取废止号。"""
    body = (
        "原《浙江省分时电价管理办法》(浙发改价格〔2024〕21号)同时废止。\n"
        "本通知由浙江省发展和改革委员会负责解释(浙发改价格规〔2026〕12号)。"
    )
    assert extract_official_number(body) == "浙发改价格规〔2026〕12号"


# ── L2 extract_luokuan_date:识别中文数字落款 ────────────────────────────

def test_luokuan_chinese_numeral_full():
    """中文数字全日期落款 → 正确解析。"""
    tail = "……自本规则印发之日起施行。\n\n国家发展和改革委员会\n二〇二三年九月十五日"
    assert extract_luokuan_date(tail) == "2023-09-15"


def test_luokuan_chinese_numeral_month_only_fixes_year():
    """P_2027_NDRC_572b0ea8:落款'二〇二三年九月'(无日)→ 年份必须修成 2023(当前抓不到→None)。"""
    tail = "……自2027年1月1日起施行。\n\n国家发展和改革委员会\n二〇二三年九月"
    out = extract_luokuan_date(tail)
    assert out is not None and out.startswith("2023-09")
