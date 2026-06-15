"""Step 4.5: 元数据抽取(从 fetched body)+ news_filter 二轮(含 issuer 维度)。"""
from __future__ import annotations
import json
from pathlib import Path

from .metadata_extractor import extract_meta
from .news_filter import is_news_or_press


def extract_all(in_dir: Path, out_dir: Path, quarantine_jsonl: Path) -> tuple:
    """返回 (extracted, quarantined)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    quarantined = 0
    quar_lines: list = []
    for f in in_dir.glob("*.json"):
        row = json.loads(f.read_text(encoding="utf-8"))
        if not row.get("body"):
            continue
        meta = extract_meta(url=row["url"], title=row["title"], body=row["body"])
        # 二轮 news_filter(此时有 issuer)
        check = is_news_or_press(url=meta.url, title=meta.title, issuer=meta.issuer)
        # 入库前最后拦截:issuer_unknown(已抓正文 issuer 该有却没有)+
        # 非政策类型标题(采购/党建/列表行)。后者在 Step 3 多已拦下,这里兜底
        # run_pipeline 批量 backfill——它不过 policy_gate,Step 3/4.5 是唯一防线。
        hard = [r for r in check.reasons
                if r == "issuer_unknown"
                or r.startswith("non_policy_title")
                or r == "non_policy_list_row"]
        if hard:
            quar_lines.append(json.dumps({
                "url": meta.url, "title": meta.title,
                "drop_reasons": check.reasons,
            }, ensure_ascii=False))
            quarantined += 1
            continue
        outf = out_dir / f.name
        outf.write_text(json.dumps({
            "url": meta.url, "title": meta.title,
            "official_number": meta.official_number,
            "date": meta.date or row.get("date_hint", ""),
            "issuer": meta.issuer,
            "city": row.get("city", ""),
            "city_code": row.get("city_code", ""),
            "province": row.get("province", ""),
            "channel_type": row.get("channel_type", ""),
            "body": row["body"],
            "via": row.get("via", ""),
        }, ensure_ascii=False), encoding="utf-8")
        extracted += 1
    with open(quarantine_jsonl, "a", encoding="utf-8") as qf:
        if quar_lines:
            qf.write("\n".join(quar_lines) + "\n")
    return extracted, quarantined
