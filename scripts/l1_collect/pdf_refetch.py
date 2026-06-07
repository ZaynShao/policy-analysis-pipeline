"""母文件重抓:body被截断(只抓到封面)的政策,从同一source_url重抓补全。
护栏:单调只增(新严格更长+同源才写)、谓词候选(非pid清单)、幂等、记provenance。§C合规。"""
from __future__ import annotations
import os
import re
import requests
from pathlib import Path
from typing import Callable, Optional

THIN_THRESHOLD = 800
PDF_URL_RE = re.compile(r"\.pdf(\?|$)", re.I)
TIMEOUT = 60


def _body_chars(content: str) -> int:
    parts = content.split("---", 2)
    body = parts[2] if len(parts) >= 3 else content
    return len(body.strip())


def should_refetch_text(content: str) -> bool:
    return _body_chars(content) < THIN_THRESHOLD


def should_refetch(policy_path: Path) -> bool:
    return should_refetch_text(policy_path.read_text(encoding="utf-8"))


def _fetch_via_pdfplumber(url: str) -> Optional[str]:
    if not PDF_URL_RE.search(url):
        return None
    try:
        import pdfplumber, io
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code >= 400:
            return None
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        return text if len(text) >= 200 else None
    except Exception:
        return None


def _fetch_via_firecrawl(url: str) -> Optional[str]:
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            json={"url": url, "formats": ["markdown"]},
            headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        md = (resp.json().get("data") or {}).get("markdown") or ""
        return md if len(md) >= 200 else None
    except Exception:
        return None


def fetch_pdf_content(url: str) -> Optional[str]:
    return _fetch_via_pdfplumber(url) or _fetch_via_firecrawl(url)


def upgrade_policy_body(policy_path: Path,
                        fetch_fn: Callable[[str], Optional[str]] = fetch_pdf_content) -> dict:
    content = policy_path.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {"upgraded": False, "reason": "no_frontmatter"}
    front, body_old = parts[1], parts[2]
    m = re.search(r"^source_url:\s*(.+)$", front, re.M)
    if not m:
        return {"upgraded": False, "reason": "no_source_url"}
    url = m.group(1).strip()
    new_body = fetch_fn(url)
    if not new_body:
        return {"upgraded": False, "reason": "fetch_failed", "url": url}
    old_chars = len(body_old.strip())
    new_chars = len(new_body.strip())
    if new_chars <= old_chars:                       # 单调护栏:永不缩短/替换
        return {"upgraded": False, "reason": "not_longer",
                "old_chars": old_chars, "new_chars": new_chars}
    policy_path.write_text(f"---{front}---\n\n{new_body.strip()}\n", encoding="utf-8")
    return {"upgraded": True, "old_chars": old_chars, "new_chars": new_chars, "url": url}
