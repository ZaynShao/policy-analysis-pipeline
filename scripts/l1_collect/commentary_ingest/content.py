"""FeedItem 正文提取:优先用 feed 全文;缺失/过短时兜底抓 URL(限速/退避)。

§6.2:正文兜底抓取走 mp.weixin.qq.com,限速 + 随机延迟 + 退避;失败标记不硬刚。
随机延迟用 time.sleep,延迟量由调用方按 index 错开(本模块固定区间)。
"""
from __future__ import annotations

import time

import requests
import trafilatura
from bs4 import BeautifulSoup

from .models import FeedItem

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 微信已知失败壳页标记(确定性,非 LLM)。这些页能过字数门但是垃圾。
GARBAGE_MARKERS = (
    "环境异常", "请在微信客户端打开", "请在微信打开",
    "该内容已被发布者删除", "此内容因违规无法查看", "内容已被删除",
    "参数错误", "该公众号已迁移", "已被发布者删除",
)


def html_to_text(html: str) -> str:
    """HTML → 纯文本。trafilatura 优先,bs4 兜底。"""
    if not html:
        return ""
    extracted = trafilatura.extract(html, include_comments=False,
                                    include_tables=False)
    if extracted and extracted.strip():
        return extracted.strip()
    return BeautifulSoup(html, "html.parser").get_text("\n").strip()


def is_low_quality(text: str, min_len: int = 200) -> bool:
    """正文不可用?过短,或短文本命中微信失败标记。长正文偶含短语不算。"""
    if len(text) < min_len:
        return True
    if len(text) < 500 and any(m in text for m in GARBAGE_MARKERS):
        return True
    return False


def is_deleted_shell(text: str) -> bool:
    """正文是否为微信删除/违规壳页(命中标记的短文本)。区别于一般过短/抓取失败。"""
    return len(text) < 500 and any(m in text for m in GARBAGE_MARKERS)


def _refetch(url: str, timeout: int, delay: float) -> str:
    """限速兜底抓正文;任何失败返回 ''。"""
    time.sleep(delay)
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        return ""
    return html_to_text(resp.text)


def to_body(item: FeedItem, *, fetch_fallback: bool = True,
            min_len: int = 200, timeout: int = 30,
            delay: float = 4.0) -> tuple:
    """返回 (body, source)。source ∈ {'feed','refetch','deleted','empty'}。

    'deleted' = 命中微信删除/违规壳页(永久,调用方不应重试);
    'empty'   = 正文过短/抓取失败(瞬时,调用方应下轮重试);
    确定性内容质量门:feed 全文过短或命中壳页 → 兜底抓 URL;仍不合格按上述区分。
    """
    body = html_to_text(item.content_html)
    if not is_low_quality(body, min_len):
        return body, "feed"
    if is_deleted_shell(body):
        return "", "deleted"
    if fetch_fallback:
        refetched = _refetch(item.url, timeout, delay)
        if not is_low_quality(refetched, min_len):
            return refetched, "refetch"
        if is_deleted_shell(refetched):
            return "", "deleted"
    return "", "empty"
