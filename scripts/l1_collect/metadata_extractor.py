"""元数据抽取:全 regex + canonical lookup,无 LLM(LESSONS B1)。"""
from __future__ import annotations
import re
from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Optional

# 文号 regex(支持〔〕 / [] / () 三种括号)
_OFFNUM_RE = re.compile(r"[一-龥]{2,8}[〔\[(]\s*(?:19|20)\d{2}\s*[〕\])]\s*\d+\s*号")
_OFFNUM_RE_LOOSE = re.compile(r"[一-龥]{0,8}[〔\[(]\s*(?:19|20)\d{2}\s*[〕\])]\s*\d+\s*号")

_DATE_URL_RE = re.compile(r"/((?:19|20)\d{2})[-_/](\d{1,2})[-_/](\d{1,2})/")
_DATE_BODY_CN = re.compile(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})")
_DATE_BODY_ISO = re.compile(r"((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})")

# 中央部委 issuer canonical 表(市级补由 channel_catalog 反查时补)
ISSUER_DOMAIN_TABLE = {
    "www.gov.cn": "国务院",
    "www.ndrc.gov.cn": "国家发展和改革委员会",
    "www.nea.gov.cn": "国家能源局",
    "www.miit.gov.cn": "工业和信息化部",
    "www.mofcom.gov.cn": "商务部",
    "www.mohurd.gov.cn": "住房和城乡建设部",
    "www.mee.gov.cn": "生态环境部",
    "www.mof.gov.cn": "财政部",
}


@dataclass
class ExtractedMeta:
    title: str = ""
    official_number: str = ""
    date: str = ""
    issuer: Optional[str] = None
    url: str = ""


def extract_official_number(text: str) -> str:
    if not text:
        return ""
    m = _OFFNUM_RE.search(text)
    if m:
        return m.group(0).replace(" ", "")
    m = _OFFNUM_RE_LOOSE.search(text)
    return m.group(0).replace(" ", "") if m else ""


def extract_date(url: str, body: str = "") -> str:
    """优先 URL path,其次正文中文/ISO 日期。返回 YYYY-MM-DD 或 ''。"""
    if url:
        m = _DATE_URL_RE.search(url)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    if body:
        m = _DATE_BODY_CN.search(body) or _DATE_BODY_ISO.search(body)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return ""


def extract_issuer_from_url(url: str) -> Optional[str]:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return None
    return ISSUER_DOMAIN_TABLE.get(host)


def extract_meta(url: str, title: str, body: str) -> ExtractedMeta:
    return ExtractedMeta(
        title=title.strip(),
        official_number=extract_official_number(body),
        date=extract_date(url, body),
        issuer=extract_issuer_from_url(url),
        url=url,
    )
