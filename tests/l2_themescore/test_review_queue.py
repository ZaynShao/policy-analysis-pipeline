import json
from pathlib import Path
from scripts.l2_themescore.models import QueueRecord
from scripts.l2_themescore.review_queue import write_queue

def test_write_queue(tmp_path):
    out = tmp_path/"q.jsonl"
    n = write_queue([QueueRecord(pid="P1", stage="program_gate", reason="registry:未知 theme",
                                 detail={"bad":["x"]})], str(out))
    assert n == 1
    rows = [json.loads(l) for l in Path(out).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["pid"] == "P1" and rows[0]["stage"] == "program_gate"
