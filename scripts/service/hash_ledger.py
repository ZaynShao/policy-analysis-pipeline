"""Content-hash 增量账本。hash 或 pipeline_version 变化 → 需要重建。"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class LedgerEntry:
    pid: str
    raw_content_hash: str
    pipeline_version: int


def compute_hash(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def load_ledger(path: Path) -> dict[str, LedgerEntry]:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {pid: LedgerEntry(**e) for pid, e in data.items()}


def save_ledger(path: Path, entries: dict[str, LedgerEntry]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {pid: asdict(e) for pid, e in entries.items()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def needs_rebuild(pid: str, raw_text: str, current_version: int,
                  ledger: dict[str, LedgerEntry]) -> bool:
    entry = ledger.get(pid)
    if entry is None:
        return True
    if entry.pipeline_version != current_version:
        return True
    return entry.raw_content_hash != compute_hash(raw_text)


def mark_done(ledger: dict[str, LedgerEntry], pid: str, raw_text: str, version: int) -> None:
    ledger[pid] = LedgerEntry(pid, compute_hash(raw_text), version)
