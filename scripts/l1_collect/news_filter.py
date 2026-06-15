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

# 非政策类型标题黑名单(确定性、高精度)。这些类型的标题在政府站属于
# 采购/招投标、党建活动、新闻/报告发布,绝不会是规范性政策公文。
# 政府域名 + 政府 issuer 时旧逻辑一律放行,本黑名单是唯一确定性拦截。
# 精度优先:误杀=真政策被静默丢,故只收录几乎不可能出现在政策标题里的标记词
# (如"年度报告"会命中《企业年度报告公示办法》这类真政策,故不收;模糊的报告
#  发布交由 policy_gate 的 LLM 裁决)。
NON_POLICY_TITLE_MARKERS = (
    # 采购 / 招投标
    "中标公告", "中标结果", "中标候选", "成交公告", "招标公告", "采购公告",
    "询价公告", "竞争性磋商", "竞争性谈判", "单一来源", "中选公告",
    "废标公告", "流标公告", "资格预审", "比选公告",
    # 新闻 / 报告发布
    "新闻发布会", "例行新闻发布", "白皮书", "蓝皮书",
    # 党建 / 活动
    "大学习", "大讨论", "大提升", "主题党日", "党史学习教育",
    "表彰大会", "誓师大会", "文艺汇演", "演讲比赛",
)
# 非政策标题正则(需上下文判断,不能用纯子串)。当前仅"成果物发布通告":
# "发布……报告》/报告(年份"——报告是被发布的带书名号/年份戳的成果物,而非
# 规范性公文。要求紧跟 》或(,且有"发布"语境,以避开"年度报告公示办法/报送
# 工作"这类真政策(报告后接 公示办法/报送 等收束词,不匹配)。
NON_POLICY_TITLE_PATTERNS = (
    re.compile(r"发布.{0,40}报告[》(（]"),
)
# 框线符(U+2500–U+257F):列表页/侧边栏导航行被当成文章抓下的结构特征,
# 真政策标题永不含此类字符。注意只匹配框线符,不碰 U+0085(NEL)等控制符
# (那是合法政策标题里可能内嵌的字符,见 step3_filter 的 NEL 回归测试)。
_BOX_DRAWING_RE = re.compile(r"[─-╿]")

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
    for marker in NON_POLICY_TITLE_MARKERS:
        if marker in title:
            reasons.append(f"non_policy_title:{marker}")
            break
    else:
        for pat in NON_POLICY_TITLE_PATTERNS:
            if pat.search(title):
                reasons.append(f"non_policy_title:{pat.pattern}")
                break
    if _BOX_DRAWING_RE.search(title):
        reasons.append("non_policy_list_row")
    if not _issuer_is_gov(issuer):
        if _is_gov_domain(url) and issuer is None:
            reasons.append("issuer_unknown_but_gov_domain")
        else:
            reasons.append("issuer_unknown")
    return FilterResult(is_filtered=bool(reasons), reasons=reasons)
