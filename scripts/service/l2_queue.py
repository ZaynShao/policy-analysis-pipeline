"""持久化优先级队列。手动(high)插队，cron(normal)批量；单 worker 串行消费。"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path

_PRIORITY_RANK = {"high": 0, "normal": 1}


@dataclass
class QueueItem:
    pid: str
    trigger: str     # "manual" | "cron" | "l1_incremental"
    priority: str    # "high" | "normal"
    requested_at: str


def read_queue(path: Path) -> list[QueueItem]:
    path = Path(path)
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(QueueItem(**json.loads(line)))
    return items


def _write_all(path: Path, items: list[QueueItem]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(i), ensure_ascii=False) for i in items]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def enqueue(path: Path, item: QueueItem) -> None:
    items = read_queue(path)
    for existing in items:
        if existing.pid == item.pid:
            # 去重；若新条目优先级更高则升级
            if _PRIORITY_RANK[item.priority] < _PRIORITY_RANK[existing.priority]:
                existing.priority = item.priority
                existing.trigger = item.trigger
                existing.requested_at = item.requested_at
                _write_all(path, items)
            return
    items.append(item)
    _write_all(path, items)


def enqueue_batch(path: Path, pids: list[str], trigger: str, priority: str,
                  requested_at: str) -> None:
    for pid in pids:
        enqueue(path, QueueItem(pid, trigger, priority, requested_at))


def next_item(path: Path) -> QueueItem | None:
    items = read_queue(path)
    if not items:
        return None
    # 稳定排序保 FIFO；按优先级 rank 取最高
    indexed = sorted(enumerate(items), key=lambda t: (_PRIORITY_RANK[t[1].priority], t[0]))
    return indexed[0][1]


def mark_complete(path: Path, pid: str) -> None:
    items = [i for i in read_queue(path) if i.pid != pid]
    _write_all(path, items)
