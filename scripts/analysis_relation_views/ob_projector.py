"""OB 双链投影器 — canonical 边集 → _rev_<pid>.md 反链页。

严格按 SCHEMA §5.3 的「命名与图谱兜底」配方(复刻 legacy build_reverse_links.py,
不照搬、不 import):

  1. 文件名 `_rev_<pid>.md`(**绝不裸 {pid}.md**)
     —— 裸命名会截胡所有 [[P_xxx]],使 raw 政策在 graph view 孤岛(P_2026_MIIT_13)。
  2. body 顶部一行 `[[<raw file_stem>|<显示名>]]` 作图谱边锚点
     —— alias 在 graph view 不建边,显式 file_stem link 才 100% 建边。
  3. 段内每条链接用显式 `[[<peer file_stem>|<peer_pid>]]`
     —— file_stem 与 id 解耦、不随 id 漂移,比裸 [[P_xxx]] 可靠。
  4. 全量重生:先清空已有 _rev_*.md(带「路径含 _index_by_policy」安全闸),再写。

file_stem 一律从当前 raw index 现查,无独立缓存表。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .models import (
    REL_TO_INBOUND_LABEL,
    REL_TO_OUTBOUND_LABEL,
    SECTION_ORDER,
    RelEdge,
)
from .raw_index import RawMeta

CST = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _peer_link(peer_pid: str, raw_index: dict[str, RawMeta]) -> str:
    """显式 [[stem|pid]];peer 必在 raw(dangling 已在 merge 阶段剔除)。"""
    meta = raw_index.get(peer_pid)
    stem = meta.file_stem if meta else ""
    return f"[[{stem}|{peer_pid}]]" if stem else f"[[{peer_pid}]]"


def _render_section(lines: list[str], label: str, edges: list, raw_index, peer_attr: str):
    """渲染一个 section。edges 已排序,peer_attr='from_id'(入向) 或 'to_id'(出向)。"""
    lines.append(f"## {label} — {len(edges)}")
    lines.append("")
    for e in edges:
        peer_pid = getattr(e, peer_attr)
        peer_meta = raw_index.get(peer_pid)
        ptitle = (peer_meta.title if peer_meta else "").strip()
        pdate = ((peer_meta.date if peer_meta else "") or "")[:10] or "—"
        link = _peer_link(peer_pid, raw_index)
        if ptitle:
            lines.append(f"- {link} — {ptitle} ({pdate})")
        else:
            lines.append(f"- {link} ({pdate})")
    lines.append("")


def render_page(
    pid: str,
    inbound: dict[str, list[RelEdge]],
    outbound: dict[str, list[RelEdge]],
    raw_index: dict[str, RawMeta],
) -> str:
    """生成单篇 _rev_<pid>.md 的文本内容(确定性,幂等)。"""
    meta = raw_index.get(pid)
    title = meta.title if meta else ""
    file_stem = meta.file_stem if meta else ""

    in_count = sum(len(v) for v in inbound.values())
    out_count = sum(len(v) for v in outbound.values())

    fm = {
        "policy_id": pid,
        "title": title,
        "inbound_edge_count": in_count,
        "outbound_edge_count": out_count,
        "last_updated": _now_iso(),
    }
    fm_yaml = yaml.safe_dump(
        fm, allow_unicode=True, default_flow_style=False, sort_keys=False
    ).rstrip()

    lines = ["---", fm_yaml, "---", ""]

    # body 顶部图谱边锚点:显式 file_stem link 到 raw 政策(alias 在 graph view 不建边)。
    if file_stem:
        lines.append(f"> 政策原文:[[{file_stem}|{title or pid}]]")
        lines.append("")

    if in_count:
        lines.append(f"# 入向反链:{pid}")
        lines.append("")
        for rel in SECTION_ORDER:
            if rel in inbound and inbound[rel]:
                _render_section(
                    lines, REL_TO_INBOUND_LABEL[rel], inbound[rel], raw_index, "from_id"
                )

    if out_count:
        lines.append(f"# 出向引用:{pid}")
        lines.append("")
        for rel in SECTION_ORDER:
            if rel in outbound and outbound[rel]:
                _render_section(
                    lines, REL_TO_OUTBOUND_LABEL[rel], outbound[rel], raw_index, "to_id"
                )

    return "\n".join(lines) + "\n"


def _group_edges(edges: list[RelEdge]):
    """边集 → inbound[to][rel]=[...], outbound[from][rel]=[...],段内按 peer.date 倒序。"""
    inbound: dict[str, dict[str, list[RelEdge]]] = {}
    outbound: dict[str, dict[str, list[RelEdge]]] = {}
    for e in edges:
        outbound.setdefault(e.from_id, {}).setdefault(e.rel, []).append(e)
        inbound.setdefault(e.to_id, {}).setdefault(e.rel, []).append(e)
    return inbound, outbound


def _date_of(raw_index, pid: str) -> str:
    m = raw_index.get(pid)
    return (m.date if m else "") or ""


def project_pages(
    edges: list[RelEdge],
    raw_index: dict[str, RawMeta],
    out_dir: Path,
) -> dict:
    """全量重生 _rev_*.md。先清空(带安全闸)再写。返回统计。"""
    # ── 安全闸:输出目录路径必须含 _index_by_policy,否则中止(防误删) ──
    if "_index_by_policy" not in str(out_dir):
        print(f"[fatal] 输出目录路径异常,拒绝清空/写入: {out_dir}", file=sys.stderr)
        raise SystemExit(2)

    out_dir.mkdir(parents=True, exist_ok=True)
    removed = 0
    for old in out_dir.glob("_rev_*.md"):
        old.unlink()
        removed += 1

    inbound, outbound = _group_edges(edges)
    all_pids = set(inbound) | set(outbound)

    # 段内按 peer.date 倒序(确定性:同日期再按 peer pid 升序兜底,保证幂等)
    for pid in inbound:
        for rel in inbound[pid]:
            inbound[pid][rel].sort(
                key=lambda e: (_date_of(raw_index, e.from_id), e.from_id), reverse=True
            )
    for pid in outbound:
        for rel in outbound[pid]:
            outbound[pid][rel].sort(
                key=lambda e: (_date_of(raw_index, e.to_id), e.to_id), reverse=True
            )

    written = 0
    for pid in sorted(all_pids):
        text = render_page(
            pid, inbound.get(pid, {}), outbound.get(pid, {}), raw_index
        )
        (out_dir / f"_rev_{pid}.md").write_text(text, encoding="utf-8")
        written += 1

    return {"pages_written": written, "old_removed": removed}
