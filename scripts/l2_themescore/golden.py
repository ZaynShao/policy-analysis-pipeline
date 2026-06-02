import json
from pathlib import Path
from .models import GoldenRecord

def load_golden(path: str) -> list:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out.append(GoldenRecord(
            pid=d["pid"], gold_themes=d.get("gold_themes", d.get("themes", [])),
            gold_primary=d.get("gold_primary", d.get("primary_theme", "")),
            gold_scores=d.get("gold_scores", d.get("scores", {})),
            gold_影响分析=d.get("gold_影响分析", d.get("影响分析")),
            is_planted=bool(d.get("is_planted", False)), error_type=d.get("error_type")))
    return out

def score_judge(rows) -> dict:
    """rows: list[(pid, verdict, is_planted)]. 召回/精度。"""
    planted = [r for r in rows if r[2]]
    rejected = [r for r in rows if r[1] == "reject"]
    caught = [r for r in rejected if r[2]]
    recall = len(caught) / len(planted) if planted else 0.0
    precision = len(caught) / len(rejected) if rejected else 1.0
    return {"recall": recall, "precision": precision,
            "n_planted": len(planted), "n_rejected": len(rejected), "n_caught": len(caught)}
