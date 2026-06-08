"""L1 运行锁。l1_status 是唯一的 L1 运行信号，不用进程存活判断。"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class L1Status:
    status: str = "idle"                     # "running" | "idle"
    started_at: str | None = None
    completed_at: str | None = None
    pids_collected: list[str] = field(default_factory=list)


def read_status(path: Path) -> L1Status:
    path = Path(path)
    if not path.exists():
        return L1Status()
    data = json.loads(path.read_text(encoding="utf-8"))
    return L1Status(**data)


def _write(path: Path, st: L1Status) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(st), ensure_ascii=False, indent=2), encoding="utf-8")


def set_running(path: Path, started_at: str) -> None:
    _write(path, L1Status(status="running", started_at=started_at))


def set_idle(path: Path, completed_at: str, pids_collected: list[str]) -> None:
    prev = read_status(path)
    _write(path, L1Status(status="idle", started_at=prev.started_at,
                          completed_at=completed_at, pids_collected=list(pids_collected)))


def is_running(path: Path) -> bool:
    return read_status(path).status == "running"
