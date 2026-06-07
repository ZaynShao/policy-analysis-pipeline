"""commentary_ingest 全包共享数据类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass
class FeedItem:
    """一条 wewe-rss feed 文章(已解析)。"""
    id: str                 # 22 位微信短链 hash
    url: str                # https://mp.weixin.qq.com/s/{id}
    title: str
    content_html: str       # fulltext 模式下的正文 HTML;可能为空
    date_published: str     # YYYY-MM-DD,缺失为 ""
    source_account: str     # 公众号名


class Disposition(str, Enum):
    INGEST = "ingest"            # 入 vault commentaries
    SKIP_JUNK = "skip_junk"      # 完全丢弃
    MARKET_INTEL = "market_intel"  # 暂存 state,等 B1


@dataclass
class Classification:
    disposition: Disposition
    reasons: list = field(default_factory=list)
