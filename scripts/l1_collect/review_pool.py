"""L1 review pool:所有"机器拿不准"项的统一进池(IN)。只写不排——
人交互面 + 标准化回灌消费者交 B14。本模块只负责 append(去重)/load/summarize。

OUT 契约(文档化"将来正式回灌消费什么";本线不建消费者,过渡用现有 oneshots):
  记录格式 {ref, kind, verdict, corrections?, reviewer, note, decided_run}
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / "state" / "l1_review" / "pool.jsonl"

# 每 kind 允许的人工裁决(供 B14 标准化 + 将来回灌消费者)
VERDICTS = {
    "gate": ("pass", "commentary", "reject"),
    "checkpoint": ("promote", "drop"),
    "sweep": ("confirm", "keep"),
    "fetch_fail": ("retry", "unfetchable", "drop"),
}

_KEYS = ("kind", "ref", "reason", "suggested_action", "confidence",
         "evidence", "channel", "run_label")


def load(pool_path: Path = POOL) -> list:
    if not pool_path.exists():
        return []
    out = []
    for line in pool_path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            out.append(json.loads(line))
    return out


def append(entry: dict, pool_path: Path = POOL) -> bool:
    """按 (kind, ref) 去重写入。已存在→跳过返回 False。"""
    key = (entry.get("kind"), entry.get("ref"))
    for r in load(pool_path):
        if (r.get("kind"), r.get("ref")) == key:
            return False
    row = {k: entry.get(k) for k in _KEYS}
    pool_path.parent.mkdir(parents=True, exist_ok=True)
    with open(pool_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True


def summarize(pool_path: Path = POOL) -> dict:
    out: dict = {}
    for r in load(pool_path):
        k = r.get("kind", "?")
        out[k] = out.get(k, 0) + 1
    return out
