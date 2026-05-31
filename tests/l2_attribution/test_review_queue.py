import json
from pathlib import Path
from scripts.l2_attribution.models import ResolvedIdentity
from scripts.l2_attribution.review_queue import write_queue


def test_write_queue_one_line_per_conflict(tmp_path):
    ri1 = ResolvedIdentity(pid="P_a")
    ri1.add_conflict("issuer", "转载", {"title_issuer": "国务院办公厅"})
    ri2 = ResolvedIdentity(pid="P_b")
    ri2.add_conflict("_all", "非gov域名", {"url": "https://x.in-en.com"})
    out = tmp_path / "q.jsonl"
    n = write_queue([ri1, ri2], str(out))
    assert n == 2
    lines = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["pid"] == "P_a" and lines[0]["field"] == "issuer"
    assert lines[1]["field"] == "_all"
