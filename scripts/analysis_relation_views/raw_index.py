"""从当前 raw 现读 pid → {title, file_stem, date}。

SCHEMA §5.3 硬约束:**勿引入 pid→stem 缓存表**(当年回归放大器)。
每次重生都从当前 raw 现读;查不到 pid = dangling。
file_stem = 文件名去 .md(中文标题哈希名),与 id 解耦、不随 id 漂移。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.l1_audit.corpus import load_policies


@dataclass(frozen=True)
class RawMeta:
    title: str
    file_stem: str
    date: str


def load_raw_index(vault: Path) -> dict[str, RawMeta]:
    """现读 0_raw/policies/*.md → {pid: RawMeta}。"""
    index: dict[str, RawMeta] = {}
    for rec in load_policies(f"{vault}/0_raw/policies"):
        if not rec.pid:
            continue
        index[rec.pid] = RawMeta(
            title=rec.title or "",
            file_stem=Path(rec.path).stem,
            date=str(rec.date or ""),
        )
    return index
