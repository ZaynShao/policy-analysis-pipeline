"""去重台账:已见 source_url 集合(vault 现有 + 历史 ledger)+ 处置记录 + last_run。

去重主键 = source_url。vault 现有 283 篇预先存在(早于本 ledger),故每轮都
扫 vault commentary frontmatter 取 source_url,叠加 ledger,保证幂等。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
_SRC_URL_RE = re.compile(r"^source_url:\s*(\S+)\s*$", re.MULTILINE)


def load_seen_urls(vault_dir: Path, state_dir: Path) -> set:
    seen = set()
    com_dir = Path(vault_dir) / "0_raw" / "commentaries"
    if com_dir.exists():
        for f in com_dir.glob("*.md"):
            m = _SRC_URL_RE.search(f.read_text(encoding="utf-8", errors="ignore"))
            if m:
                seen.add(m.group(1))
    ledger = Path(state_dir) / "commentary_ingest" / "processed_ids.jsonl"
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                url = json.loads(line).get("url")
            except json.JSONDecodeError:
                continue
            if url:
                seen.add(url)
    return seen


def record_dispositions(state_dir: Path, entries: list) -> None:
    out = Path(state_dir) / "commentary_ingest"
    out.mkdir(parents=True, exist_ok=True)
    ledger = out / "processed_ids.jsonl"
    ts = datetime.now(CST).isoformat(timespec="seconds")
    with ledger.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps({**e, "ts": ts}, ensure_ascii=False) + "\n")


def write_last_run(state_dir: Path, summary: dict) -> None:
    out = Path(state_dir) / "commentary_ingest"
    out.mkdir(parents=True, exist_ok=True)
    rec = {"ran_at": datetime.now(CST).isoformat(timespec="seconds"), **summary}
    (out / "last_run.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
