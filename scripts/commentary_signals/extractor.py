from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path

import yaml


POLICY_ID_RE = re.compile(r"P_[A-Za-z0-9_]+")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

ROLE_KEYWORDS = {
    "risk": ["风险", "不确定", "压力", "亏损", "下调", "受限", "冲击", "挑战", "瓶颈", "阻力", "担忧", "短期难"],
    "opportunity": ["机会", "利好", "增长", "空间", "补贴", "收益", "商业模式", "需求", "优势", "窗口"],
    "execution": ["落地", "执行", "推进", "试点", "建设", "项目", "招标", "并网", "实施", "配置", "运行"],
    "attention": ["关注", "热议", "看点", "解读", "问答", "一图读懂", "研讨", "观察"],
}


@dataclass
class CommentaryDoc:
    path: Path
    root: Path
    relative_path: str
    frontmatter: dict
    body: str


@dataclass
class CommentarySignal:
    commentary_id: str
    path: str
    title: str
    related_policy_ids: list[str]
    theme_ids: list[str]
    signal_role: str
    confidence: float
    evidence: str
    source_account: str
    source_type: str
    business_tag: str

    def to_dict(self) -> dict:
        return {
            "commentary_id": self.commentary_id,
            "path": self.path,
            "title": self.title,
            "related_policy_ids": self.related_policy_ids,
            "theme_ids": self.theme_ids,
            "signal_role": self.signal_role,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "source_account": self.source_account,
            "source_type": self.source_type,
            "business_tag": self.business_tag,
        }


def commentary_id(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:12]
    return f"C_{digest}"


def parse_markdown(path: Path, root: Path) -> CommentaryDoc:
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            frontmatter = yaml.safe_load(parts[1]) or {}
            body = parts[2]
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    return CommentaryDoc(
        path=path,
        root=root,
        relative_path=rel,
        frontmatter=frontmatter if isinstance(frontmatter, dict) else {},
        body=body.strip(),
    )


def related_policy_ids(frontmatter: dict) -> list[str]:
    raw = frontmatter.get("related_policy")
    values = raw if isinstance(raw, list) else [raw]
    out = []
    seen = set()
    for value in values:
        if value in (None, "", [], {}):
            continue
        for pid in POLICY_ID_RE.findall(str(value)):
            if pid not in seen:
                out.append(pid)
                seen.add(pid)
    return out


def _title(doc: CommentaryDoc) -> str:
    title = doc.frontmatter.get("title")
    return sanitize_text(str(title)).strip() if title else doc.path.stem


def sanitize_text(text: str) -> str:
    text = CONTROL_CHAR_RE.sub(" ", str(text))
    text = text.replace("\ufffd", " ")
    return re.sub(r"\s+", " ", text).strip()


def is_readable_body(body: str) -> bool:
    if not body.strip():
        return True
    head = body[:500]
    if "%PDF-" in head or "\x00" in head or "\ufffd" in head:
        return False
    sample = body[:1000]
    printable = sum(1 for char in sample if char.isprintable() or char.isspace())
    return printable / max(len(sample), 1) >= 0.96


def _compact(text: str) -> str:
    return sanitize_text(text)


def _classify_role(text: str) -> tuple[str, str]:
    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            if keyword and keyword in text:
                return role, keyword
    return "interpretation", ""


def _match_themes(text: str, theme_aliases: dict[str, list[str]]) -> list[str]:
    out = []
    seen = set()
    lower_text = text.lower()
    for theme_id, aliases in theme_aliases.items():
        terms = [theme_id] + list(aliases or [])
        if any(str(term).strip() and str(term).strip().lower() in lower_text for term in terms):
            if theme_id not in seen:
                out.append(theme_id)
                seen.add(theme_id)
    return out


def _evidence(text: str, keyword: str) -> str:
    compact = _compact(text)
    if not compact:
        return ""
    if not keyword or keyword not in compact:
        return compact[:120]
    idx = compact.find(keyword)
    start = max(0, idx - 45)
    end = min(len(compact), idx + 75)
    return compact[start:end]


def _confidence(role: str, theme_ids: list[str]) -> float:
    if role != "interpretation" and theme_ids:
        return 0.72
    if role != "interpretation":
        return 0.62
    if theme_ids:
        return 0.60
    return 0.52


def extract_commentary_signal(doc: CommentaryDoc, theme_aliases: dict[str, list[str]]) -> CommentarySignal | None:
    if doc.frontmatter.get("not_policy_related") is True:
        return None
    policies = related_policy_ids(doc.frontmatter)
    if not policies:
        return None

    title = _title(doc)
    body_readable = is_readable_body(doc.body)
    text = _compact(f"{title} {doc.body if body_readable else ''}")
    role, role_keyword = _classify_role(text)
    theme_ids = _match_themes(text, theme_aliases)
    evidence = (
        f"正文不可读; 仅保留标题线索: {title[:100]}"
        if not body_readable
        else _evidence(text, role_keyword)
    )
    return CommentarySignal(
        commentary_id=commentary_id(doc.path, doc.root),
        path=doc.relative_path,
        title=title,
        related_policy_ids=policies,
        theme_ids=theme_ids,
        signal_role=role,
        confidence=_confidence(role, theme_ids),
        evidence=evidence,
        source_account=sanitize_text(doc.frontmatter.get("source_account") or ""),
        source_type=sanitize_text(doc.frontmatter.get("source_type") or ""),
        business_tag=sanitize_text(doc.frontmatter.get("business_tag") or ""),
    )
