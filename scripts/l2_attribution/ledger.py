from __future__ import annotations
import json
from pathlib import Path


def load_ledger(path: str) -> dict:
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out[d["pid"]] = d
    return out


def issuer_short_of_id(pid: str) -> str:
    """P_YYYY_<SHORT>_<hash>[_suffix] -> SHORT。"""
    parts = (pid or "").split("_")
    return parts[2] if len(parts) >= 4 else ""


def cross_check(new_id: str, ledger_entry: dict):
    """resolver 的新 id 前缀 vs ledger suggested_issuer_short。"""
    r = issuer_short_of_id(new_id)
    l = ledger_entry.get("suggested_issuer_short", "")
    if r == l:
        return "agree", None
    return "disagree", {"resolver": r, "ledger": l,
                        "ledger_region": ledger_entry.get("true_region", "")}
