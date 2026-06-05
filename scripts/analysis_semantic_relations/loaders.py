from __future__ import annotations
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from scripts.l1_audit.corpus import load_policies

BASIS_RELS = {"cites_basis", "references"}  # ③-B 里指向上位文件的信号


@dataclass(frozen=True)
class PolicyView:
    pid: str
    title: str
    region_level: str
    region_name: str
    issuer: str
    year: int | None
    themes: list
    primary_theme: str
    importance: int | None


def _year_of(date_str: str) -> int | None:
    m = re.search(r"(19|20)\d{2}", str(date_str or ""))
    return int(m.group(0)) if m else None


def _norm_issuer(value) -> str:
    """Normalize issuer to a clean string.

    None/missing -> ""; list -> join non-empty members with '·'; scalar -> str().strip().
    Empty must stay falsy ("").
    """
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
        return "·".join(parts)
    return str(value).strip()


def _raw_views(vault: Path) -> list[PolicyView]:
    out = []
    for rec in load_policies(f"{vault}/0_raw/policies"):
        fm = rec.raw_fm or {}
        region = fm.get("region") or {}
        out.append(PolicyView(
            pid=rec.pid,
            title=rec.title,
            region_level=str(region.get("level", "")),
            region_name=str(region.get("name", "")),
            issuer=_norm_issuer(fm.get("issuer")),
            year=_year_of(fm.get("date", "")),
            themes=[],
            primary_theme="",
            importance=None,
        ))
    return out


def load_policy_views(
    policies: list[PolicyView] | None = None,
    vault: Path = None,
) -> dict[str, PolicyView]:
    """Load PolicyViews, overlaying themes/primary_theme/importance from business_view YAMLs.

    policies can be injected (for tests); otherwise loaded from raw vault.
    """
    base = policies if policies is not None else _raw_views(Path(vault))
    bv_dir = Path(vault) / "_meta" / "business_view"
    by_pid: dict[str, PolicyView] = {}
    for v in base:
        doc = {}
        f = bv_dir / f"{v.pid}.yaml"
        if f.exists():
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        by_pid[v.pid] = replace(
            v,
            themes=list(doc.get("themes", []) or []),
            primary_theme=str(doc.get("primary_theme", "") or ""),
            importance=doc.get("重要性"),
        )
    return by_pid


def load_hpr_basis_pairs(hpr_path: Path) -> set[tuple[str, str]]:
    """Read (from, to) pairs from ③-B high-precision candidates as derives_from basis signals."""
    pairs: set[tuple[str, str]] = set()
    if not Path(hpr_path).exists():
        return pairs
    for line in Path(hpr_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("rel") in BASIS_RELS:
            pairs.add((row.get("from"), row.get("to")))
    return pairs
