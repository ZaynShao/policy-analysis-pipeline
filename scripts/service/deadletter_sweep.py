"""L2 死信 sweep 回队。纯 stdlib,cron 友好:永不 raise,恒 exit 0。"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.service import l2_queue, notify


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def plan_sweep(
    dead_records: list[dict],
    history: dict[str, int],
    max_retries: int = 2,
    cap: int = 50,
) -> tuple[list[str], list[str], dict]:
    """死信记录 → (回队 pid,放弃 pid,新 history)。pid 去重保序。"""
    new_history = dict(history)
    requeue: list[str] = []
    givenup: list[str] = []
    seen: set[str] = set()

    for rec in dead_records:
        pid = rec.get("pid")
        if not isinstance(pid, str) or not pid or pid in seen:
            continue
        seen.add(pid)
        if int(history.get(pid, 0)) >= max_retries:
            givenup.append(pid)
            continue
        if len(requeue) >= cap:
            continue
        requeue.append(pid)
        new_history[pid] = int(history.get(pid, 0)) + 1
    return requeue, givenup, new_history


def _run(state_dir: Path, max_retries: int, cap: int) -> dict:
    dead_path = state_dir / "l2_failures.jsonl"
    queue_path = state_dir / "l2_queue.jsonl"
    history_path = state_dir / "l2_sweep_history.json"
    archived_path = state_dir / "l2_failures.archived.jsonl"

    records = _read_jsonl(dead_path)
    if not records:
        return {"swept": 0}

    history = _read_json(history_path, {})
    requeue, givenup, new_history = plan_sweep(records, history, max_retries, cap)
    processed = set(requeue) | set(givenup)
    archived = [row for row in records if row.get("pid") in processed]
    left = [row for row in records if row.get("pid") not in processed]

    if requeue:
        l2_queue.enqueue_batch(
            queue_path,
            requeue,
            trigger="sweep",
            priority="normal",
            requested_at=_utc_now(),
        )
    _append_jsonl(archived_path, archived)
    _write_jsonl(dead_path, left)
    _write_json(history_path, new_history)
    if givenup:
        notify.send_text(f"[S2] 死信放弃重试 {len(givenup)} 条: {','.join(givenup)}")
    return {
        "swept": len(processed),
        "requeued": len(requeue),
        "givenup": len(givenup),
        "left": len(left),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--cap", type=int, default=50)
    args = ap.parse_args(argv)

    try:
        summary = _run(Path(args.state_dir), args.max_retries, args.cap)
    except Exception as e:
        summary = {"swept": 0, "error": str(e)[:300]}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
