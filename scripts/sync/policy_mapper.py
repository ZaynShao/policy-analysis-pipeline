"""business_view YAML(dict) → Policy 行 dict。纯函数，映射契约见 spec §5.4。"""
from __future__ import annotations
import datetime
import json
import re


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


def parse_issue_date(s: str) -> datetime.date:
    """YYYY-MM-DD → date;空/非法 → raise ValueError(不写假数据)。"""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        raise ValueError(f"unparseable issue date: {s!r}")
    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def map_policy_row(bv: dict, core: dict, pipeline_version: int) -> dict:
    """business_view(分析) + raw 核心字段 → 完整 Policy 行。
    核心字段坏掉(坏 date / 空 title / 空 content)→ raise ValueError,由 collect 拒收+记池。"""
    issue_date = parse_issue_date(core.get("date"))          # 可能 raise
    title = (core.get("title") or "").strip()
    content = (core.get("content") or "").strip()
    if not title:
        raise ValueError("empty title")
    if not content:
        raise ValueError("empty content")
    row = map_business_view(bv, pipeline_version)            # pipeline 字段
    row.update({
        "title": title,
        "issuer": core.get("issuer") or "",                 # 空 issuer 允许空串(过 NOT NULL)
        "issue_date": issue_date,                            # date 对象,psycopg2 自适配
        "content": content,
        "source": "AUTO",                                   # 都是 L1 自动采集
        "doc_number": core.get("doc_number") or None,
        "source_url": core.get("source_url") or None,
        "region": core.get("region") or None,
        "level": core.get("level") or None,
    })
    return row
