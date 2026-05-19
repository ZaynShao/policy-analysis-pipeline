"""政策 vs 新闻稿 确定性过滤。

规则(全部确定性,不上 LLM):
  1. 域名黑名单(媒体域名)
  2. 标题特征(_市县后缀 / [XX网] 前缀 / 国际X网)
  3. issuer 必须是政府机关(关键字 lookup,缺失标 issuer_unknown)

本阶段不开 override(2026-05-19 user 决策),接受被误杀。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from urllib.parse import urlparse
import re
from typing import Optional

DOMAIN_BLACKLIST = {
    "xinhuanet.com", "people.com.cn", "cctv.com", "thepaper.cn",
    "sohu.com", "sina.com.cn", "163.com", "qq.com", "ifeng.com",
    "escn.com.cn", "in-en.com", "bjx.com.cn",
    "credit.sh.gov.cn", "credit.beijing.gov.cn",
}

GOV_DOMAIN_SUFFIXES = (".gov.cn", ".org.cn")

TITLE_BAD_PATTERNS = [
    re.compile(r"_市县$"),
    re.compile(r"^\[\w+网\]"),
    re.compile(r"国际\w{1,4}网"),
]

GOV_ISSUER_KEYWORDS = (
    "委", "局", "部", "院", "司", "厅", "办公厅", "政府", "国务院",
    "管理委员会", "管委会",
)


@dataclass
class FilterResult:
    is_filtered: bool
    reasons: list = field(default_factory=list)


def _domain_blocked(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    return any(host == d or host.endswith("." + d) for d in DOMAIN_BLACKLIST)


def _is_gov_domain(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    return any(host.endswith(s) for s in GOV_DOMAIN_SUFFIXES)


def _issuer_is_gov(issuer: Optional[str]) -> bool:
    if not issuer:
        return False
    return any(kw in issuer for kw in GOV_ISSUER_KEYWORDS)


def is_news_or_press(url: str, title: str, issuer: Optional[str]) -> FilterResult:
    reasons: list = []
    if _domain_blocked(url):
        reasons.append("domain_blacklist")
    for pat in TITLE_BAD_PATTERNS:
        if pat.search(title):
            reasons.append(f"title_pattern:{pat.pattern}")
            break
    if not _issuer_is_gov(issuer):
        if _is_gov_domain(url) and issuer is None:
            reasons.append("issuer_unknown_but_gov_domain")
        else:
            reasons.append("issuer_unknown")
    return FilterResult(is_filtered=bool(reasons), reasons=reasons)
