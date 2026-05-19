"""HTTP 联通性测试 + 列表页结构启发式判定。

启发式逻辑:
- 信号 1:页面含"下一页"/翻页字样 + 任何 <a>
- 信号 2:≥3 个 <a> 邻近文本含日期模式(20XX 年/月/日)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import re
from typing import Literal, Optional
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; ZCE-Probe/0.1; +https://github.com/)"
TIMEOUT = 15
CST = timezone(timedelta(hours=8))

ProbeVerdict = Literal["ok", "http_error", "structure_unknown", "empty"]


@dataclass
class ProbeResult:
    url: str
    http_status: Optional[int]
    page_has_list_pattern: bool
    verdict: ProbeVerdict
    error: str = ""
    probed_at: str = ""


_DATE_NEAR_LINK_RE = re.compile(r"20\d{2}[-/年.]\s*\d{1,2}[-/月.]\s*\d{1,2}")


def looks_like_list_page(html: str) -> bool:
    """启发式判断是否列表页。"""
    soup = BeautifulSoup(html, "html.parser")
    txt = soup.get_text(" ", strip=True)
    if any(kw in txt for kw in ["下一页", "下页", "末页"]):
        if soup.find_all("a"):
            return True
    links = soup.find_all("a")
    near_date = 0
    for a in links:
        parent_text = (a.parent.get_text(" ", strip=True) if a.parent else "")[:200]
        if _DATE_NEAR_LINK_RE.search(parent_text):
            near_date += 1
        if near_date >= 3:
            return True
    return False


def probe_url(url: str) -> ProbeResult:
    now = datetime.now(CST).isoformat(timespec="seconds")
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    except Exception as e:
        return ProbeResult(
            url=url, http_status=None, page_has_list_pattern=False,
            verdict="http_error", error=str(e)[:200], probed_at=now,
        )
    if resp.status_code >= 400:
        return ProbeResult(
            url=url, http_status=resp.status_code, page_has_list_pattern=False,
            verdict="http_error", probed_at=now,
        )
    text = resp.text or ""
    if not text.strip():
        return ProbeResult(
            url=url, http_status=resp.status_code, page_has_list_pattern=False,
            verdict="empty", probed_at=now,
        )
    has_list = looks_like_list_page(text)
    return ProbeResult(
        url=url, http_status=resp.status_code, page_has_list_pattern=has_list,
        verdict="ok" if has_list else "structure_unknown", probed_at=now,
    )
