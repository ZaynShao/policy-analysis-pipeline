from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import yaml


EXPECTED_IMPACT_KEYS = {"加油", "充电", "电力_储能_V2G_交易"}
CURRENT_EXTRACTED_BY = "scripts/l2_themescore/run_2b.py"
DEPRECATED_IMPACT_KEYS = {"乡村", "乡village"}


@dataclass
class BusinessViewDecision:
    pid: str
    path: str
    action: str
    reasons: list[str]
    extracted_by: Optional[str]
    extracted_model: Optional[str]
    impact_keys: list[str]
    sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_path(path: Path, vault: Path) -> str:
    try:
        return str(path.relative_to(vault))
    except ValueError:
        return str(path)


def _manual(path: Path, vault: Path, reasons: list[str], pid: Optional[str] = None) -> BusinessViewDecision:
    return BusinessViewDecision(
        pid=pid or path.stem,
        path=_relative_path(path, vault),
        action="manual_review",
        reasons=reasons,
        extracted_by=None,
        extracted_model=None,
        impact_keys=[],
        sha256=_sha256(path),
    )


def inspect_business_view(path: Path, vault: Path) -> BusinessViewDecision:
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return _manual(path, vault, [f"yaml_parse_error:{exc.__class__.__name__}"])

    pid = data.get("pid")
    if not pid:
        return _manual(path, vault, ["missing_pid"])
    if path.stem != pid:
        return _manual(path, vault, ["pid_filename_mismatch"], pid=str(pid))

    extracted_by = data.get("extracted_by")
    extracted_model = data.get("extracted_model")
    impact = data.get("影响分析")
    impact_keys = sorted(impact.keys()) if isinstance(impact, dict) else []
    reasons: list[str] = []

    is_current_flow = extracted_by == CURRENT_EXTRACTED_BY
    if not is_current_flow:
        reasons.append("legacy_extracted_by")
    if (not is_current_flow) and extracted_model in (None, "", "unknown_legacy", "claude-opus-4-7-via-subagent"):
        reasons.append("legacy_model")
    if DEPRECATED_IMPACT_KEYS & set(impact_keys):
        reasons.append("deprecated_xiangcun_key")
    if impact_keys and set(impact_keys) != EXPECTED_IMPACT_KEYS:
        reasons.append("impact_schema_mismatch")

    action = "isolate_legacy" if reasons else "keep_current"
    if action == "keep_current":
        reasons = ["current_flow"]

    return BusinessViewDecision(
        pid=str(pid),
        path=_relative_path(path, vault),
        action=action,
        reasons=reasons,
        extracted_by=str(extracted_by) if extracted_by is not None else None,
        extracted_model=str(extracted_model) if extracted_model is not None else None,
        impact_keys=impact_keys,
        sha256=_sha256(path),
    )


def inventory_business_views(vault: Path) -> list[BusinessViewDecision]:
    bv_dir = vault / "_meta" / "business_view"
    return [inspect_business_view(path, vault) for path in sorted(bv_dir.glob("*.yaml"))]


def summarize(decisions: list[BusinessViewDecision]) -> dict:
    by_action = Counter(decision.action for decision in decisions)
    by_reason = Counter(reason for decision in decisions for reason in decision.reasons)
    by_extracted_by = Counter((decision.extracted_by or "") for decision in decisions)
    by_extracted_model = Counter((decision.extracted_model or "") for decision in decisions)
    return {
        "total": len(decisions),
        "by_action": dict(sorted(by_action.items())),
        "by_reason": dict(sorted(by_reason.items())),
        "by_extracted_by": dict(by_extracted_by.most_common()),
        "by_extracted_model": dict(by_extracted_model.most_common()),
    }
