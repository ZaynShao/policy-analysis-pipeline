"""取 wewe-rss JSON feed 并解析成 FeedItem 列表。

接口契约:wewe-rss JSON Feed 1.1。字段以 Task 1 捕获的真实结构为准;
本实现对 content_html/content_text、authors/author 做兼容兜底。
"""
from __future__ import annotations

import json

import requests

from .models import FeedItem

WEIXIN_PERMALINK = "https://mp.weixin.qq.com/s/{}"


def _norm_date(raw: str) -> str:
    """ISO datetime/date 取前 10 位当 YYYY-MM-DD(feed 保证 ISO 格式);空值返回 ''。"""
    if not raw:
        return ""
    return str(raw)[:10] if len(str(raw)) >= 10 else ""


def _account_name(item: dict) -> str:
    authors = item.get("authors")
    if isinstance(authors, list) and authors and isinstance(authors[0], dict):
        return authors[0].get("name", "") or ""
    author = item.get("author")
    if isinstance(author, dict):
        return author.get("name", "") or ""
    return item.get("author_name", "") or ""


def _content(item: dict) -> str:
    return item.get("content_html") or item.get("content_text") or ""


def parse_feed(json_text: str) -> list:
    """JSON feed 文本 → list[FeedItem]。"""
    data = json.loads(json_text)
    out = []
    for item in data.get("items", []):
        aid = item.get("id", "")
        # 容错:某些 feed 的 id 是整段 url,抽末段 hash
        if "/" in aid:
            aid = aid.rstrip("/").split("/")[-1]
        url = item.get("url") or WEIXIN_PERMALINK.format(aid)
        out.append(FeedItem(
            id=aid,
            url=url,
            title=(item.get("title") or "").strip(),
            content_html=_content(item),
            # 实测 wewe-rss 用 date_modified(非标准 date_published),两者兼容兜底
            date_published=_norm_date(item.get("date_published") or item.get("date_modified") or ""),
            source_account=_account_name(item),
        ))
    return out


def fetch_feed(feed_url: str, auth_code: str = "", timeout: int = 30) -> list:
    """HTTP 拉 feed → list[FeedItem]。auth_code 走 Bearer 头。"""
    headers = {"Authorization": f"Bearer {auth_code}"} if auth_code else {}
    resp = requests.get(feed_url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return parse_feed(resp.text)
