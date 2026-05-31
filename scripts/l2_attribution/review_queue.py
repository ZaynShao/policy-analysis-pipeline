from __future__ import annotations
import json
from pathlib import Path
from scripts.l2_attribution.models import QueueRecord


def write_queue(resolved_list, out_path: str) -> int:
    """每个 conflict 一行 jsonl。返回写出条数。"""
    recs = []
    for ri in resolved_list:
        for c in ri.conflicts:
            recs.append(QueueRecord(pid=ri.pid, field=c.field,
                                    reason=c.reason, signals=c.signals))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(out_path).open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    return len(recs)
