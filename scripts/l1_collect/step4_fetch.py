"""Step 4: 抓取候选政策的正文。"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from .fetcher import fetch_article


def fetch_candidates(in_jsonl: Path, out_dir: Path, error_log: Path) -> tuple:
    """返回 (success, error)。"""
    success = 0
    error = 0
    errors: list = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for line in in_jsonl.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        row = json.loads(line)
        url = row.get("url", "")
        res = fetch_article(url)
        if res.via == "fetch_error":
            res = fetch_article(url)          # 浅重试一次(瞬时失败兜底)
        fid = hashlib.sha1(url.encode()).hexdigest()[:16]
        outf = out_dir / f"{fid}.json"
        outf.write_text(json.dumps({
            "url": url,
            "title": row.get("title", ""),
            "date_hint": row.get("date_hint", ""),
            "city": row.get("city", ""),
            "city_code": row.get("city_code", ""),
            "province": row.get("province", ""),
            "channel_type": row.get("channel_type", ""),
            "via": res.via,
            "body": res.body,
        }, ensure_ascii=False), encoding="utf-8")
        if res.via == "fetch_error":
            errors.append(url)
            error += 1
        else:
            success += 1
    error_log.write_text("\n".join(errors), encoding="utf-8")
    return success, error
