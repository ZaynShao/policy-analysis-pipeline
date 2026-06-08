"""Step 5: 入 vault raw。"""
from __future__ import annotations
import json
from pathlib import Path

from .ingester import ingest_one, validate_with_schema, POLICIES_DIR


def ingest_extracted(in_dir: Path, ingest_log: Path, out_dir: Path = None) -> tuple:
    """返回 (ingested, failed)。out_dir 覆盖写入目录(默认 POLICIES_DIR)。"""
    ingested = 0
    failed = 0
    logs: list = []
    for f in in_dir.glob("*.json"):
        row = json.loads(f.read_text(encoding="utf-8"))
        try:
            md_path = ingest_one(
                url=row["url"], title=row["title"],
                official_number=row.get("official_number", ""),
                date=row.get("date", ""), issuer=row.get("issuer"),
                body=row["body"],
                city=row.get("city") or None,
                city_code=row.get("city_code") or None,
                province=row.get("province") or None,
                channel_type=row.get("channel_type") or None,
                via=row.get("via", "trafilatura"),
                out_dir=out_dir or POLICIES_DIR,
            )
            ok = validate_with_schema(md_path)
            if not ok:
                md_path.unlink()
                failed += 1
                logs.append({"url": row["url"], "result": "schema_fail"})
                continue
            ingested += 1
            logs.append({
                "url": row["url"], "result": "ok", "file": md_path.name,
                "city": row.get("city", ""),
            })
        except Exception as e:
            failed += 1
            logs.append({"url": row["url"], "result": "error", "error": str(e)[:200]})
    ingest_log.parent.mkdir(parents=True, exist_ok=True)
    ingest_log.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in logs),
        encoding="utf-8",
    )
    return ingested, failed
