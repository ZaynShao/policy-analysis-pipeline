import json
from pathlib import Path

def write_queue(records, out_path: str) -> int:
    """records: list[QueueRecord]. 一条一行 JSONL。返回条数。"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(out_path).open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    return len(records)
