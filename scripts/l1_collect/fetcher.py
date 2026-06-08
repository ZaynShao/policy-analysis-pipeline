"""抓取兜底链:Firecrawl → trafilatura → BeautifulSoup → fetch_error。

Firecrawl 是商业 API,需要 env var 配置 key,无 key 时跳过(本阶段默认无 key)。
trafilatura + BS4 走纯本地 HTTP。
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional
import requests

MIN_BODY_LEN = 500  # 短于此视为抓取失败(摘要而非全文)
UA = "Mozilla/5.0 (compatible; ZCE-Fetcher/0.1)"
TIMEOUT = 30


@dataclass
class FetchResult:
    url: str
    via: str
    body: Optional[str]
    raw_html: Optional[str] = None


def _fetch_via_firecrawl(url: str) -> Optional[str]:
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            json={"url": url, "formats": ["markdown"]},
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        md = (data.get("data") or {}).get("markdown") or ""
        return md if len(md) >= MIN_BODY_LEN else None
    except Exception:
        return None


def _fetch_via_trafilatura(url: str) -> Optional[str]:
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(
            downloaded, include_comments=False, include_tables=True,
        )
        return text if text and len(text) >= MIN_BODY_LEN else None
    except Exception:
        return None


def _fetch_via_bs4(url: str) -> Optional[str]:
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if resp.status_code >= 400:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        return text if len(text) >= MIN_BODY_LEN else None
    except Exception:
        return None


def fetch_article(url: str) -> FetchResult:
    for via, fn in [
        ("firecrawl", _fetch_via_firecrawl),
        ("trafilatura", _fetch_via_trafilatura),
        ("bs4", _fetch_via_bs4),
    ]:
        body = fn(url)
        if body:
            return FetchResult(url=url, via=via, body=body)
    return FetchResult(url=url, via="fetch_error", body=None)
