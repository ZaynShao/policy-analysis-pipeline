"""L2 死信增长告警。纯 stdlib,cron 友好:永不 raise,恒 exit 0。"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.service import notify


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records


def _read_last_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    try:
        return int(data.get("last_count", 0))
    except Exception:
        return 0


def _write_state(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_count": count, "checked_at": _utc_now()}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def _format_latest(records: list[dict]) -> str:
    parts = []
    for rec in records[-2:]:
        pid = str(rec.get("pid", ""))
        error = str(rec.get("error", ""))[:300]
        parts.append(f"{pid}: {error}")
    return "; ".join(parts)


def check_growth(dead_path: Path, state_path: Path) -> str | None:
    """对比死信行数与上次记录;增长告警,否则仅更新 state。绝不 raise。"""
    try:
        dead_path = Path(dead_path)
        state_path = Path(state_path)
        records = _read_records(dead_path)
        count = len(records)
        last_count = _read_last_count(state_path)
        _write_state(state_path, count)
        if count > last_count:
            latest = _format_latest(records)
            return f"[S2] L2 死信增长 {last_count}→{count}; 最新: {latest}"
        return None
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", required=True)
    args = ap.parse_args(argv)

    state_dir = Path(args.state_dir)
    dead_path = state_dir / "l2_failures.jsonl"
    state_path = state_dir / "deadletter_alert_state.json"
    msg = check_growth(dead_path, state_path)
    notified = False
    if msg:
        notified = notify.send_text(msg)
    dead_count = len(_read_records(dead_path))
    print(json.dumps({"dead_count": dead_count, "grew": bool(msg), "notified": notified}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
