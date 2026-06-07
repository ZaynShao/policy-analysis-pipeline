"""统一结构性过滤(账号无关,不打 per-account 补丁)。

两层(spec §5):
  1. SKIP_JUNK:招聘 / 节日 / 纯视频 / 活动征集 —— 完全丢弃
  2. MARKET_INTEL:采购招标+容量数字 / IPO融资 / 出货数据 —— 暂存等 B1
其余 → INGEST(保守多收,相关性留 L2)。

只看 title;不做能源相关性判断(那是 L2)。
"""
from __future__ import annotations

import re

from .models import Classification, Disposition, FeedItem

SKIP_PATTERNS = [
    (re.compile(r"招聘|诚聘|岗位招募|招募"), "招聘"),
    (re.compile(r"节快乐|放假通知|假期安排|祝.{0,4}节"), "节日"),
    (re.compile(r"^视频[：:]|^\s*视频\s*[:：]"), "纯视频"),
    (re.compile(r"活动征集|报名通道|诚邀参加|征集启事"), "活动通知"),
]


def _is_market_intel(title: str) -> str:
    """命中返回原因字符串,否则 ''。"""
    has_capacity = re.search(r"\d+\s*(MW|GW|GWh|MWh)", title, re.IGNORECASE)
    has_procure = re.search(r"中标|开标|采购公告|招标公告|招标|EPC|中标公示|开标公示", title)
    if has_capacity and has_procure:
        return "采购招标+容量"
    if re.search(r"采购公告|招标公告|中标公示|开标公示", title):
        return "采购招标公示"
    if re.search(r"IPO|上市|完成.{0,6}融资|融资|过会", title):
        return "资本市场动态"
    if re.search(r"出货.{0,8}(GWh|GW|万|亿)|同比增长.*%", title):
        return "出货/增速数据"
    return ""


def classify(item: FeedItem) -> Classification:
    title = item.title or ""
    for pat, reason in SKIP_PATTERNS:
        if pat.search(title):
            return Classification(Disposition.SKIP_JUNK, [reason])
    mi = _is_market_intel(title)
    if mi:
        return Classification(Disposition.MARKET_INTEL, [mi])
    return Classification(Disposition.INGEST, [])
