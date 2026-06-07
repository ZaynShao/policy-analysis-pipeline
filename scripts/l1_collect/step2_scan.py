"""Step 2: 渠道扫描。

输入:channel_catalog status=验证 + 该 batch 的 cities
输出:state/T1_scan_raw/<city>__<channel_type>__<root_domain>.jsonl

⚠ ScanRow 含 city + city_code(原 plan review 标记的修复:让 city info 沿
Step 2→5 流水线透传,避免 Step 5 ingester id 标错 issuer_short)。
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from .channel_catalog import Channel, ChannelStatus

UA = "Mozilla/5.0 (compatible; ZCE-Scan/0.1)"
TIMEOUT = 20
MAX_PAGES = 5
NEW_RATIO_THRESHOLD = 0.10
CST = timezone(timedelta(hours=8))

KEYWORDS = (
    "能源", "电力", "电网", "油气", "成品油", "充电", "储能",
    "新能源", "双碳", "光伏", "风电", "氢能", "天然气", "汽车以旧换新",
    "新型电力", "虚拟电厂", "需求响应", "碳达峰", "碳中和",
    # 召回偏向补漏(L1体检暴露的盲词)
    "换电", "现货市场", "绿证", "绿电", "车网互动", "V2G",
    "配电网", "分布式", "加氢", "抽水蓄能", "需求侧", "电价",
)

_DATE_RE = re.compile(r"((?:19|20)\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")


@dataclass
class ScanRow:
    title: str
    url: str
    date_hint: str
    source_channel: str    # root_domain
    city: str              # 透传:Step 5 ingester id 用
    city_code: str
    province: str
    channel_type: str
    scanned_at: str


LIST_MIN_TEXT = 500   # BS4 文本短于此视为空壳/JS页 → firecrawl 兜底


def _bs4_get(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code >= 400:
            return ""
        return r.text or ""
    except Exception:
        return ""


def _firecrawl_get_html(url: str) -> str:
    import os
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return ""
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            json={"url": url, "formats": ["html"]},
            headers={"Authorization": f"Bearer {key}"}, timeout=45,
        )
        if resp.status_code != 200:
            return ""
        d = resp.json().get("data") or {}
        return d.get("html") or d.get("rawHtml") or ""
    except Exception:
        return ""


def _fetch_list_html(url: str) -> str:
    """分层:BS4免费先试;空壳/反爬 → firecrawl渲染兜底。"""
    html = _bs4_get(url)
    soup = BeautifulSoup(html, "html.parser") if html else None
    text_len = len(soup.get_text(strip=True)) if soup else 0
    if text_len >= LIST_MIN_TEXT:
        return html
    fc = _firecrawl_get_html(url)
    return fc or html


def _page_urls(list_url: str, max_pages: int = MAX_PAGES) -> list:
    """政府站常见翻页:index.html / index_1.html / index_2.html ... + ?page= 兜底。"""
    urls = [list_url]
    if list_url.endswith("index.html"):
        base = list_url[: -len("index.html")]
        for n in range(1, max_pages):
            urls.append(f"{base}index_{n}.html")
    else:
        for n in range(2, max_pages + 1):
            sep = "&" if "?" in list_url else "?"
            urls.append(f"{list_url}{sep}page={n}")
    return urls


def _extract_list_items(html: str, base_url: str, ch: Channel) -> list[ScanRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[ScanRow] = []
    now = datetime.now(CST).isoformat(timespec="seconds")
    seen_urls: set = set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not title or len(title) < 5 or len(title) > 200:
            continue
        if not any(kw in title for kw in KEYWORDS):
            continue
        href = a["href"]
        if href.startswith("javascript:") or href.startswith("#") or href.startswith("mailto:"):
            continue
        url = urljoin(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        ctx = (a.parent.get_text(" ", strip=True) if a.parent else "")[:200]
        m = _DATE_RE.search(ctx)
        date_hint = ""
        if m:
            y, mo, d = m.groups()
            try:
                date_hint = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            except Exception:
                pass
        rows.append(ScanRow(
            title=title, url=url, date_hint=date_hint,
            source_channel=ch.root_domain,
            city=ch.city, city_code=ch.city_code,
            province=ch.province, channel_type=ch.channel_type,
            scanned_at=now,
        ))
    return rows


def scan_channel(ch: Channel, out_dir: Path) -> int:
    """扫单渠道,翻页直至 max_pages 或新增比 < threshold。返回入库行数。"""
    if ch.status != ChannelStatus.验证:
        return 0
    all_rows: list[ScanRow] = []
    seen_urls: set = set()
    for page_url in _page_urls(ch.list_url):
        html = _fetch_list_html(page_url)
        if not html:
            break
        rows = _extract_list_items(html, page_url, ch)
        new_rows = [x for x in rows if x.url not in seen_urls]
        for x in new_rows:
            seen_urls.add(x.url)
        all_rows.extend(new_rows)
        if rows and (len(new_rows) / max(1, len(rows))) < NEW_RATIO_THRESHOLD:
            break

    out_dir.mkdir(parents=True, exist_ok=True)
    fn = out_dir / f"{ch.city}__{ch.channel_type}__{ch.root_domain}.jsonl"
    fn.write_text(
        "\n".join(json.dumps(asdict(x), ensure_ascii=False) for x in all_rows),
        encoding="utf-8",
    )
    return len(all_rows)
