from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import re
from pathlib import Path

import yaml


CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

SIGNAL_KEYWORDS = [
    ("capacity_disclosure", ["可开放容量", "容量表", "开放容量"]),
    ("price_signal", ["价格调整", "调价", "汽、柴油价格", "柴油价格", "汽油价格"]),
    ("subsidy_list", ["补贴清单", "奖补", "补贴"]),
    ("trading_result", ["交易", "成交", "挂牌"]),
    ("tender_procurement", ["招标", "采购", "公开遴选", "设计-采购", "EPC"]),
    ("competitive_allocation", ["竞配", "竞争性配置", "评分结果", "回收指标"]),
    ("project_list", ["项目清单", "清单公示"]),
    ("pilot_landing", ["试点", "落地", "示范", "投运", "首个"]),
    ("project_commissioned", ["并网", "建成", "投产", "上线", "全容量"]),
    ("market_access", ["许可", "批准证书", "经营网点"]),
    ("project_progress", ["推进", "调度", "座谈", "进展"]),
    ("project_case", ["典型案例", "入选"]),
]

BUSINESS_LINE_BY_THEME = {
    "charging_infra": ["charging"],
    "residential_charging": ["charging"],
    "v2g": ["charging", "power"],
    "vpp_theme": ["power"],
    "aggregator_access": ["power"],
    "power_market": ["power"],
    "energy_storage_theme": ["power"],
    "green_power_trading_theme": ["power"],
    "distribution_grid_opening": ["power"],
    "carbon_market_theme": ["power"],
    "gas_station_transition_theme": ["fuel"],
    "petroleum_retail_compliance": ["fuel"],
}


@dataclass
class PolicyDoc:
    path: Path
    root: Path
    relative_path: str
    frontmatter: dict
    body: str


@dataclass
class MarketSignal:
    market_signal_id: str
    source_pid: str
    current_policy_id: str
    raw_path: str
    title: str
    region: dict
    theme_ids: list[str]
    business_lines: list[str]
    signal_type: str
    observed_date: str
    time_validity: str
    related_policy_ids: list[str]
    confidence: float
    evidence: str
    source_url: str

    def to_dict(self) -> dict:
        return {
            "market_signal_id": self.market_signal_id,
            "source_pid": self.source_pid,
            "current_policy_id": self.current_policy_id,
            "raw_path": self.raw_path,
            "title": self.title,
            "region": self.region,
            "theme_ids": self.theme_ids,
            "business_lines": self.business_lines,
            "signal_type": self.signal_type,
            "observed_date": self.observed_date,
            "time_validity": self.time_validity,
            "related_policy_ids": self.related_policy_ids,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "source_url": self.source_url,
        }


def sanitize_text(text) -> str:
    text = CONTROL_CHAR_RE.sub(" ", str(text or ""))
    text = text.replace("\ufffd", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_policy_file(path: Path, root: Path) -> PolicyDoc:
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            frontmatter = yaml.safe_load(text[4:end]) or {}
            body = text[end + len("\n---"):]
    return PolicyDoc(
        path=path,
        root=root,
        relative_path=path.resolve().relative_to(root.resolve()).as_posix(),
        frontmatter=frontmatter if isinstance(frontmatter, dict) else {},
        body=sanitize_text(body),
    )


def locate_policy_by_id_or_alias(policies_root: Path, pid: str) -> Path | None:
    return build_policy_index(policies_root).get(pid)


def build_policy_index(policies_root: Path) -> dict[str, Path]:
    index = {}
    for path in sorted(policies_root.glob("*.md")):
        doc = parse_policy_file(path, policies_root)
        current_id = doc.frontmatter.get("id")
        if current_id:
            index.setdefault(str(current_id), path)
        aliases = doc.frontmatter.get("aliases") or []
        if isinstance(aliases, list):
            for alias in aliases:
                if alias:
                    index.setdefault(str(alias), path)
    return index


def classify_signal_type(title: str, body: str) -> str:
    title = sanitize_text(title)
    for signal_type, keywords in SIGNAL_KEYWORDS:
        if any(keyword in title for keyword in keywords):
            return signal_type
    text = f"{title} {body}"
    for signal_type, keywords in SIGNAL_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return signal_type
    return "unknown"


def match_themes(text: str, theme_aliases: dict[str, list[str]]) -> list[str]:
    lowered = text.lower()
    out = []
    seen = set()
    for theme_id, aliases in theme_aliases.items():
        terms = [theme_id] + list(aliases or [])
        if any(str(term).strip() and str(term).strip().lower() in lowered for term in terms):
            if theme_id not in seen:
                out.append(theme_id)
                seen.add(theme_id)
    return out


def business_lines_for(theme_ids: list[str]) -> list[str]:
    out = []
    seen = set()
    for theme_id in theme_ids:
        for line in BUSINESS_LINE_BY_THEME.get(theme_id, []):
            if line not in seen:
                out.append(line)
                seen.add(line)
    return out


def market_signal_id(source_pid: str, raw_path: str) -> str:
    digest = hashlib.sha256(f"{source_pid}|{raw_path}".encode("utf-8")).hexdigest()[:12]
    return f"MI_{digest}"


def normalize_date(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.date().isoformat() if isinstance(value, dt.datetime) else value.isoformat()
    return str(value)


def time_validity(signal_type: str, title: str, body: str) -> str:
    text = f"{title} {body}"
    if signal_type == "price_signal":
        return "price_window"
    if "季度" in text or "Q1" in text or "Q2" in text or "Q3" in text or "Q4" in text:
        return "quarterly"
    if signal_type == "unknown":
        return "unknown"
    return "point_in_time"


def _source_url(frontmatter: dict) -> str:
    provenance = frontmatter.get("provenance")
    if isinstance(provenance, dict) and provenance.get("url"):
        return sanitize_text(provenance.get("url"))
    return sanitize_text(frontmatter.get("source_url") or "")


def _region(frontmatter: dict) -> dict:
    region = frontmatter.get("region")
    if not isinstance(region, dict):
        return {"level": "", "code": "", "name": ""}
    return {
        "level": sanitize_text(region.get("level") or ""),
        "code": sanitize_text(region.get("code") or ""),
        "name": sanitize_text(region.get("name") or ""),
    }


def _confidence(signal_type: str, theme_ids: list[str], region: dict) -> float:
    score = 0.55
    if signal_type != "unknown":
        score += 0.15
    if theme_ids:
        score += 0.15
    if region.get("name") and region.get("name") != "未知":
        score += 0.05
    return round(min(score, 0.9), 2)


def _evidence(title: str, body: str) -> str:
    text = sanitize_text(f"{title} {body}")
    return text[:180]


def extract_market_signal(row: dict, doc: PolicyDoc, theme_aliases: dict[str, list[str]]) -> MarketSignal:
    title = sanitize_text(row.get("title") or doc.frontmatter.get("title") or doc.path.stem)
    text = f"{title} {doc.body}"
    theme_ids = match_themes(text, theme_aliases)
    signal_type = classify_signal_type(title, doc.body)
    region = _region(doc.frontmatter)
    observed_date = normalize_date(doc.frontmatter.get("date"))
    raw_path = doc.relative_path
    return MarketSignal(
        market_signal_id=market_signal_id(str(row["pid"]), raw_path),
        source_pid=str(row["pid"]),
        current_policy_id=sanitize_text(doc.frontmatter.get("id") or ""),
        raw_path=raw_path,
        title=title,
        region=region,
        theme_ids=theme_ids,
        business_lines=business_lines_for(theme_ids),
        signal_type=signal_type,
        observed_date=observed_date,
        time_validity=time_validity(signal_type, title, doc.body),
        related_policy_ids=[],
        confidence=_confidence(signal_type, theme_ids, region),
        evidence=_evidence(title, doc.body),
        source_url=_source_url(doc.frontmatter),
    )
