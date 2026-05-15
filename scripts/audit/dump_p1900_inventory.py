#!/usr/bin/env python3
"""
P_1900 inventory(T3 侦察产物,只读)

扫 vault `0_raw/policies/`,把 id 仍为 P_1900_* 的政策按 frontmatter 真实状态分类,
输出人类可读 markdown 报告 + 机器可读 jsonl。

分类(可重叠):
  A · classification 倒灌且 isolated_label ∈ {news_or_press, index_page}
       → 候选 archive(决策 1 选 A1)
  B · date 是 placeholder(YYYY-01-01 或 == fetched_at 同日)
       → 需要从正文/URL 重抽 date
  C · date 字段 OK 且非 placeholder,只 id 漂(走 §C 白名单 + B2 路径)
  D · date 字段真空

不修改 vault。

用法:
    python3 scripts/audit/dump_p1900_inventory.py
    python3 scripts/audit/dump_p1900_inventory.py --vault /path/to/vault
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("需要 PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

DEFAULT_VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
OUT_DIR = Path(__file__).resolve().parents[2] / "state" / "T3"

ARCHIVE_LABELS = {"news_or_press", "index_page"}


def parse_frontmatter(text: str):
    if not text.startswith("---\n"):
        return None, text
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return None, text
    fm_text = text[4:end]
    body = text[end + 5:]
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        fm = None
    return fm, body


def is_placeholder_date(date_val, fetched_at) -> str:
    """返回 placeholder 类型字符串,空串表示非 placeholder。"""
    if not date_val:
        return ""
    s = str(date_val)
    try:
        dt = datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return "unparseable"
    if dt.month == 1 and dt.day == 1:
        return "jan_1"
    if fetched_at:
        if str(fetched_at)[:10] == s:
            return "eq_fetched_day"
    return ""


def classify(fm: dict) -> dict:
    """对一条 P_1900 frontmatter 给 A/B/C/D 分类标签。"""
    flags = {"is_a": False, "is_b": False, "is_c": False, "is_d": False}
    if not isinstance(fm, dict):
        return flags

    cls = fm.get("classification") or {}
    label = cls.get("isolated_label", "")
    tags = fm.get("tags") or []
    if label in ARCHIVE_LABELS or any("classified_main_graph_exclude" in str(t) for t in tags):
        flags["is_a"] = True

    date_val = fm.get("date")
    prov = fm.get("provenance") or {}
    fetched_at = prov.get("fetched_at")

    if not date_val or str(date_val).strip() == "":
        flags["is_d"] = True
    else:
        ph = is_placeholder_date(date_val, fetched_at)
        if ph:
            flags["is_b"] = True
            flags["b_reason"] = ph
        else:
            flags["is_c"] = True
    return flags


def collect(vault: Path) -> list[dict]:
    pol_dir = vault / "0_raw" / "policies"
    rows = []
    for p in sorted(pol_dir.iterdir()):
        if not p.suffix == ".md":
            continue
        text = p.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        if not isinstance(fm, dict):
            continue
        cur_id = fm.get("id", "")
        if not str(cur_id).startswith("P_1900_"):
            continue
        flags = classify(fm)
        prov = fm.get("provenance") or {}
        cls = fm.get("classification") or {}
        rows.append({
            "filename": p.name,
            "id": cur_id,
            "title": fm.get("title", ""),
            "issuer": fm.get("issuer"),
            "date": fm.get("date"),
            "url": prov.get("url"),
            "fetched_at": prov.get("fetched_at"),
            "classification_label": cls.get("isolated_label", ""),
            "classification_action": cls.get("suggested_action", ""),
            "date_fixed_method": prov.get("date_fixed_method"),
            "is_a": flags["is_a"],
            "is_b": flags["is_b"],
            "is_c": flags["is_c"],
            "is_d": flags["is_d"],
            "b_reason": flags.get("b_reason", ""),
        })
    return rows


def _json_default(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    return str(o)


def write_jsonl(rows: list[dict], path: Path):
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=_json_default) + "\n")


def write_md_report(rows: list[dict], path: Path, vault: Path):
    n = len(rows)
    n_a = sum(1 for r in rows if r["is_a"])
    n_b = sum(1 for r in rows if r["is_b"])
    n_c = sum(1 for r in rows if r["is_c"])
    n_d = sum(1 for r in rows if r["is_d"])
    n_a_only = sum(1 for r in rows if r["is_a"] and not (r["is_b"] or r["is_c"] or r["is_d"]))
    n_a_and_b = sum(1 for r in rows if r["is_a"] and r["is_b"])

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# P_1900 Inventory · T3 侦察产物",
        "",
        f"_generated_at: {ts}_",
        f"_vault: {vault}_",
        f"_generated_by: scripts/audit/dump_p1900_inventory.py_",
        "",
        "## 总览",
        "",
        f"- 当前 vault 中 id 仍为 `P_1900_*` 的政策:**{n}** 篇",
        f"- A 类(classification 倒灌 + 标记 archive):**{n_a}** 篇",
        f"- B 类(date 是 placeholder):**{n_b}** 篇",
        f"- C 类(date OK,只 id 漂):**{n_c}** 篇",
        f"- D 类(date 字段真空):**{n_d}** 篇",
        f"- A∩B 交集:{n_a_and_b} 篇",
        f"- 仅 A 不 B/C/D:{n_a_only} 篇",
        "",
        "## A 类候选 archive 清单(决策 1 选 A1 时,这批整体迁 _archive/)",
        "",
        "| # | label | issuer | title | date | url |",
        "|---:|---|---|---|---|---|",
    ]
    a_rows = [r for r in rows if r["is_a"]]
    for i, r in enumerate(a_rows, 1):
        issuer = r["issuer"]
        if isinstance(issuer, list):
            issuer = ", ".join(issuer)
        title = (r["title"] or "")[:40].replace("|", "\\|")
        url = (r["url"] or "")[:60]
        lines.append(f"| {i} | {r['classification_label']} | {issuer} | {title} | {r['date']} | {url} |")

    lines += [
        "",
        "## B 类(date 是 placeholder,需要从正文/URL 重抽真 date)",
        "",
        "_前 30 条预览,完整在 jsonl_",
        "",
        "| # | b_reason | issuer | title | 现 date | url |",
        "|---:|---|---|---|---|---|",
    ]
    b_rows = [r for r in rows if r["is_b"]]
    for i, r in enumerate(b_rows[:30], 1):
        issuer = r["issuer"]
        if isinstance(issuer, list):
            issuer = ", ".join(issuer)
        title = (r["title"] or "")[:40].replace("|", "\\|")
        url = (r["url"] or "")[:60]
        lines.append(f"| {i} | {r['b_reason']} | {issuer} | {title} | {r['date']} | {url} |")

    lines += [
        "",
        f"## C 类(date OK 但 id 漂,B2 路径直接重算 id)· {n_c} 篇",
        "",
        "_前 20 条预览_",
        "",
        "| # | issuer | title | date | date_fixed_method |",
        "|---:|---|---|---|---|",
    ]
    c_rows = [r for r in rows if r["is_c"]]
    for i, r in enumerate(c_rows[:20], 1):
        issuer = r["issuer"]
        if isinstance(issuer, list):
            issuer = ", ".join(issuer)
        title = (r["title"] or "")[:40].replace("|", "\\|")
        lines.append(f"| {i} | {issuer} | {title} | {r['date']} | {r['date_fixed_method'] or '-'} |")

    lines += [
        "",
        f"## D 类(date 真空)· {n_d} 篇",
        "",
        "| # | issuer | title | url |",
        "|---:|---|---|---|",
    ]
    d_rows = [r for r in rows if r["is_d"]]
    for i, r in enumerate(d_rows, 1):
        issuer = r["issuer"]
        if isinstance(issuer, list):
            issuer = ", ".join(issuer)
        title = (r["title"] or "")[:60].replace("|", "\\|")
        url = (r["url"] or "")[:80]
        lines.append(f"| {i} | {issuer} | {title} | {url} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = collect(args.vault)

    jsonl = args.out_dir / "p1900_inventory.jsonl"
    md = args.out_dir / "p1900_inventory.md"
    write_jsonl(rows, jsonl)
    write_md_report(rows, md, args.vault)

    print(f"P_1900 总数: {len(rows)}")
    print(f"  A(archive 候选): {sum(1 for r in rows if r['is_a'])}")
    print(f"  B(placeholder date): {sum(1 for r in rows if r['is_b'])}")
    print(f"  C(只 id 漂): {sum(1 for r in rows if r['is_c'])}")
    print(f"  D(date 真空): {sum(1 for r in rows if r['is_d'])}")
    print(f"\nWrote:")
    print(f"  {jsonl}")
    print(f"  {md}")


if __name__ == "__main__":
    main()
