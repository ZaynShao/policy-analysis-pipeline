"""business_view YAML(dict) → Policy 行 dict。纯函数，映射契约见 spec §5.4。"""
from __future__ import annotations
import json


def importance_to_enum(score: int) -> str:
    """pipeline 1-5 分 → Prisma PolicyImportance。"""
    if score >= 5:
        return "STRATEGIC"
    if score == 4:
        return "MAJOR"
    if score == 3:
        return "GENERAL"
    return "INFO"


def map_business_view(bv: dict, pipeline_version: int) -> dict:
    primary = bv.get("primary_theme")
    comprehensive = bool(bv.get("comprehensive", False))
    themes = [
        {
            "id": t,
            "isPrimary": (t == primary),
            "isComprehensive": comprehensive and (t == primary),
        }
        for t in bv.get("themes", [])
    ]
    impact = bv.get("影响分析", {})
    impact_text = json.dumps(impact, ensure_ascii=False) if isinstance(impact, dict) else str(impact)
    return {
        "pipeline_pid": bv["pid"],
        "pipeline_version": pipeline_version,
        "importance": importance_to_enum(int(bv.get("重要性", 1))),
        "pipeline_scores": json.dumps(bv.get("scores", {}), ensure_ascii=False),
        "pipeline_themes": json.dumps(themes, ensure_ascii=False),
        "pipeline_impact": impact_text,
        "comprehensive": comprehensive,
    }
