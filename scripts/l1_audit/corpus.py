from __future__ import annotations
import re
from pathlib import Path
import yaml
from scripts.l1_audit.models import PolicyRecord

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def parse_policy_file(path: str) -> PolicyRecord | None:
    text = Path(path).read_text(encoding="utf-8")
    m = _FM_RE.search(text)
    if not m:
        return None
    fm = yaml.safe_load(m.group(1)) or {}
    body = (m.group(2) or "").lstrip("\n")
    prov = fm.get("provenance") or {}
    return PolicyRecord(
        pid=fm.get("id") or "",
        path=str(path),
        title=fm.get("title") or "",
        official_number=fm.get("official_number") or "",
        date=str(fm.get("date") or ""),
        issuer=_as_list(fm.get("issuer")),
        issuer_canonical=_as_list(fm.get("issuer_canonical")),
        url=prov.get("url") or fm.get("source_url") or "",
        body_head=body[:2000],
        raw_fm=fm,
    )


def load_policies(policies_dir: str) -> list[PolicyRecord]:
    out = []
    for f in sorted(Path(policies_dir).glob("*.md")):
        rec = parse_policy_file(str(f))
        if rec is not None:
            out.append(rec)
    return out
