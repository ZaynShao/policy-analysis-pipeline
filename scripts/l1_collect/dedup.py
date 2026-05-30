"""三维查重:URL / 文号 / 标题(LESSONS B2)。"""
from __future__ import annotations
import hashlib
import re
from urllib.parse import urlparse, urlunparse

_URL_TRAILING_SLASH = re.compile(r"/$")
_TITLE_CLEAN = re.compile(r"[\s　\(\)（）\[\]【】《》\"'：:;；,，.。!！?？\-—_]+")
_OFFNUM_CLEAN = re.compile(r"[\s\(\)（）\[\]【】〔〕年号]+")
_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                    "utm_content", "spm", "from", "ref", "fromtimestamp"}


def normalize_url(url: str) -> str:
    """归一 URL:小写 scheme/host、去 fragment、去末尾斜杠、去已知 tracking 参数。
    **保留其余 query**——政府 CMS 常把文档 id 放在 query(?id=/?contentId=),
    砍掉会把不同文档误并。原则:宁可漏并不可错并。"""
    if not url:
        return ""
    from urllib.parse import parse_qsl, urlencode
    p = urlparse(url)
    kept = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS]
    kept.sort()
    query = urlencode(kept)
    path = _URL_TRAILING_SLASH.sub("", p.path)
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", query, ""))


def normalize_official_number(s: str) -> str:
    if not s:
        return ""
    return _OFFNUM_CLEAN.sub("", s).lower()


def normalize_title(s: str) -> str:
    if not s:
        return ""
    return _TITLE_CLEAN.sub("", s).lower()


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16] if s else ""


class DedupIndex:
    def __init__(self) -> None:
        self.url_hashes: set = set()
        self.offnum_hashes: set = set()
        self.title_hashes: set = set()

    def add(self, *, url: str, official_number: str, title: str) -> None:
        h = _hash(normalize_url(url))
        if h:
            self.url_hashes.add(h)
        h = _hash(normalize_official_number(official_number))
        if h:
            self.offnum_hashes.add(h)
        h = _hash(normalize_title(title))
        if h:
            self.title_hashes.add(h)

    def is_dup(self, *, url: str, official_number: str, title: str) -> bool:
        h = _hash(normalize_url(url))
        if h and h in self.url_hashes:
            return True
        h = _hash(normalize_official_number(official_number))
        if h and h in self.offnum_hashes:
            return True
        h = _hash(normalize_title(title))
        if h and h in self.title_hashes:
            return True
        return False

    @classmethod
    def from_vault_policies(cls, vault_policies_dir) -> "DedupIndex":
        """扫 vault 现有 0_raw/policies/ 建索引。"""
        import yaml
        from pathlib import Path
        idx = cls()
        for f in Path(vault_policies_dir).glob("*.md"):
            try:
                txt = f.read_text(encoding="utf-8")[:4000]
            except Exception:
                continue
            m = re.search(r"^---\n(.*?)\n---", txt, re.S)
            if not m:
                continue
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except Exception:
                continue
            url = ((fm.get("provenance") or {}).get("url")) or ""
            offnum = fm.get("official_number") or ""
            title = fm.get("title") or ""
            idx.add(url=url, official_number=offnum, title=title)
        return idx
