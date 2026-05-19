"""写 vault/0_raw/policies/<filename>.md,过 validate_schema 校验。

ID 生成规则(对齐 SCHEMA §2):
  P_<year>_<issuer_short>_<num_or_hash>

issuer_short 来源:
  1. 中央部委 lookup table(ISSUER_SHORT_TABLE)
  2. 市级:用 city_code 前 2 位映射省级 short(BJ/SH/...),后接城市拼音 → 形如 BJ_城市码
"""
from __future__ import annotations
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import yaml

VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
POLICIES_DIR = VAULT / "0_raw" / "policies"
CST = timezone(timedelta(hours=8))

ISSUER_SHORT_TABLE = {
    "国家发展和改革委员会": "NDRC",
    "国家能源局": "NEA",
    "工业和信息化部": "MIIT",
    "商务部": "MOFCOM",
    "住房和城乡建设部": "MOHURD",
    "生态环境部": "MEE",
    "财政部": "MOF",
    "国务院": "SC",
}

# 省码(国标 6 位的前 2 位)→ short
PROVINCE_SHORT_BY_CODE = {
    "11": "BJ", "12": "TJ", "13": "HE", "14": "SX", "15": "NM",
    "21": "LN", "22": "JL", "23": "HL",
    "31": "SH", "32": "JS", "33": "ZJ", "34": "AH", "35": "FJ",
    "36": "JX", "37": "SD",
    "41": "HA", "42": "HB", "43": "HN", "44": "GD", "45": "GX",
    "46": "HI",
    "50": "CQ", "51": "SC", "52": "GZ", "53": "YN", "54": "XZ",
    "61": "SN", "62": "GS", "63": "QH", "64": "NX", "65": "XJ",
    "71": "TW", "81": "HK", "82": "MO",
}


def _issuer_short(issuer: Optional[str], city_code: Optional[str] = None,
                  channel_type: Optional[str] = None) -> str:
    if issuer and issuer in ISSUER_SHORT_TABLE:
        return ISSUER_SHORT_TABLE[issuer]
    if city_code and len(city_code) >= 2:
        prov = PROVINCE_SHORT_BY_CODE.get(city_code[:2], "OTHER")
        # 市级用 prov_<channel> 区分(避免一个市的多个 channel 撞 id)
        ct_short = {"发改委": "FGW", "能源局": "NYJ", "政府网": "GOV",
                    "经信委": "JXW", "商务局": "SWJ"}.get(channel_type or "", "X")
        return f"{prov}_{ct_short}"
    return "OTHER"


def _hash8(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:8]


def compute_pid(date: str, issuer: Optional[str], official_number: str,
                title: str, city_code: Optional[str] = None,
                channel_type: Optional[str] = None) -> str:
    year = (date or "1900").split("-")[0]
    short = _issuer_short(issuer, city_code, channel_type)
    if official_number:
        m = re.search(r"(\d+)\s*号", official_number)
        tail = m.group(1) if m else _hash8(official_number)
    else:
        tail = _hash8(f"{date}|{title}")
    return f"P_{year}_{short}_{tail}"


def _sanitize_filename(title: str) -> str:
    t = re.sub(r"[\\/:*?\"<>|]", "_", title)[:80]
    return t.strip() or "untitled"


def ingest_one(*, url: str, title: str, official_number: str, date: str,
               issuer: Optional[str], body: str,
               city: Optional[str] = None, city_code: Optional[str] = None,
               province: Optional[str] = None, channel_type: Optional[str] = None,
               via: str = "trafilatura", confidence: float = 0.85) -> Path:
    """生成 vault md 文件,返回路径。"""
    pid = compute_pid(date, issuer, official_number, title, city_code, channel_type)
    # region 推断
    if city:
        region = {"level": "市", "code": city_code or "", "name": city}
    elif issuer in ISSUER_SHORT_TABLE:
        region = {"level": "国家", "code": "000000", "name": "全国"}
    else:
        region = {"level": "", "code": "", "name": ""}
    fm = {
        "id": pid,
        "aliases": [pid],
        "title": title,
        "official_number": official_number or "",
        "issuer": [issuer] if issuer else [],
        "date": date or "",
        "region": region,
        "provenance": {
            "url": url,
            "source_type": "A",
            "fetched_via": via,
            "fetched_at": datetime.now(CST).isoformat(timespec="seconds"),
            "collected_by": "t1-city-collection",
            "collected_mode": "build-phase-manual",
            "confidence": confidence,
        },
        "type": "policy",
    }
    body_md = f"## 政策原文\n\n{body.strip()}\n"
    fn = POLICIES_DIR / f"{_sanitize_filename(title)}.md"
    n = 1
    while fn.exists():
        fn = POLICIES_DIR / f"{_sanitize_filename(title)}__{n}.md"
        n += 1
    content = "---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n" + body_md
    fn.write_text(content, encoding="utf-8")
    return fn


# 内嵌 minimal schema check(白名单 + 必填,与 audit/validate_schema.py 对齐)
# 全量 schema 校验留给 T7.3 跑完后调 validate_schema.py --vault 做最终 gate。
_FM_ALLOWED = {
    "id", "aliases", "title", "official_number", "issuer", "date",
    "region", "provenance", "issuer_canonical", "type", "subtype",
    "dup_aliases", "dedup_at", "dedup_rule", "_duplicate_of", "_duplicate_reason",
    "confidence",
}
_FM_REQUIRED = {"id", "title", "date", "region", "provenance"}


def validate_with_schema(path: Path) -> bool:
    """轻量入库校验:frontmatter 白名单 + 必填 + body 不含禁止段。"""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False
    m = re.search(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return False
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return False
    if not isinstance(fm, dict):
        return False
    keys = set(fm.keys())
    if keys - _FM_ALLOWED:
        return False
    if _FM_REQUIRED - keys:
        return False
    # body 不能含禁止段
    body = text[m.end():]
    for forbidden in ("## 摘要", "## 初步影响分析", "## 六维评分",
                      "## 业务关联", "## 跟进建议", "## 战略地位映射"):
        if forbidden in body:
            return False
    return True
