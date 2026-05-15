#!/usr/bin/env python3
"""
T2 drift inventory(只读)

精确数:
  T2a · policy 含 `tags` + `classification` 字段(LLM 派生倒灌 raw)
  T2b · commentary 缺 `title` 字段
  T2c · commentary 含 policy-only 字段(reclassified 残留)

输出 jsonl + md 报告到 state/T2/。

用法:
    python3 scripts/audit/dump_t2_inventory.py
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
    print("需要 PyYAML", file=sys.stderr)
    sys.exit(2)

DEFAULT_VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
OUT_DIR = Path(__file__).resolve().parents[2] / "state" / "T2"

# T2c policy-only 字段(SCHEMA §F 严重违反第 3 条枚举)
POLICY_ONLY_FIELDS = {
    "id", "region", "issuer", "issuer_canonical", "official_number",
    "tags",
    "_migrated_from", "_migrated_at", "_review_needed", "_review_needed_at",
}


def parse_fm(text: str):
    if not text.startswith("---\n"):
        return None
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return None
    try:
        return yaml.safe_load(text[4:end])
    except Exception:
        return None


def _json_default(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    return str(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    pol_dir = args.vault / "0_raw" / "policies"
    com_dir = args.vault / "0_raw" / "commentaries"

    # ---- T2a ----
    t2a = []
    for p in sorted(pol_dir.iterdir()):
        if p.suffix != ".md":
            continue
        text = p.read_text(encoding="utf-8")
        fm = parse_fm(text)
        if not isinstance(fm, dict):
            continue
        has_tags = "tags" in fm and fm["tags"]
        has_cls = "classification" in fm and fm["classification"]
        if has_tags or has_cls:
            cur_id = fm.get("id", "")
            label = (fm.get("classification") or {}).get("isolated_label", "") if has_cls else ""
            t2a.append({
                "filename": p.name,
                "id": cur_id,
                "has_tags": bool(has_tags),
                "has_classification": bool(has_cls),
                "classification_label": label,
                "tags_value": fm.get("tags"),
            })

    # ---- T2b ----
    t2b = []
    if com_dir.exists():
        for p in sorted(com_dir.iterdir()):
            if p.suffix != ".md":
                continue
            text = p.read_text(encoding="utf-8")
            fm = parse_fm(text)
            if not isinstance(fm, dict):
                continue
            title = fm.get("title")
            if not title or (isinstance(title, str) and not title.strip()):
                t2b.append({
                    "filename": p.name,
                })

    # ---- T2c ----
    t2c = []
    if com_dir.exists():
        for p in sorted(com_dir.iterdir()):
            if p.suffix != ".md":
                continue
            text = p.read_text(encoding="utf-8")
            fm = parse_fm(text)
            if not isinstance(fm, dict):
                continue
            present = POLICY_ONLY_FIELDS & set(fm.keys())
            if present:
                t2c.append({
                    "filename": p.name,
                    "policy_only_fields": sorted(present),
                })

    # ---- 输出 ----
    def write(rows, name):
        p = args.out_dir / f"{name}.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=_json_default) + "\n")
        return p

    p_a = write(t2a, "t2a_policy_tags_classification")
    p_b = write(t2b, "t2b_commentary_missing_title")
    p_c = write(t2c, "t2c_commentary_policy_only_fields")

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    pol_total = sum(1 for p in pol_dir.iterdir() if p.suffix == ".md")
    com_total = sum(1 for p in com_dir.iterdir() if p.suffix == ".md") if com_dir.exists() else 0

    md = args.out_dir / "t2_inventory.md"
    md.write_text(
        f"""# T2 Drift Inventory

_generated_at: {ts}_
_generated_by: scripts/audit/dump_t2_inventory.py_

## 总览

- 现存 policy 总数: **{pol_total}**
- 现存 commentary 总数: **{com_total}**

| Task | 数量 | 占比 |
|---|---:|---:|
| T2a · policy 含 tags / classification 倒灌 | **{len(t2a)}** | {len(t2a)/pol_total*100:.1f}% |
| T2b · commentary 缺 title | **{len(t2b)}** | {len(t2b)/com_total*100:.1f}% |
| T2c · commentary 含 policy-only 字段 | **{len(t2c)}** | {len(t2c)/com_total*100:.1f}% |

## 跟 STATUS 对比

| Task | STATUS 写 | 实际 | 差 |
|---|---:|---:|---:|
| T2a | 81 | {len(t2a)} | {len(t2a) - 81:+d} |
| T2b | 67 | {len(t2b)} | {len(t2b) - 67:+d} |
| T2c | 14 | {len(t2c)} | {len(t2c) - 14:+d} |

## T2c 字段命中分布

""", encoding="utf-8")

    # 写 T2c 字段分布
    from collections import Counter
    field_counts = Counter()
    for r in t2c:
        for f in r["policy_only_fields"]:
            field_counts[f] += 1
    with md.open("a", encoding="utf-8") as f:
        f.write("| 字段 | 命中 |\n|---|---:|\n")
        for k, v in field_counts.most_common():
            f.write(f"| `{k}` | {v} |\n")
        f.write("\n## T2a classification label 分布\n\n")
        label_counts = Counter()
        for r in t2a:
            label_counts[r["classification_label"] or "(no_classification)"] += 1
        f.write("| label | 命中 |\n|---|---:|\n")
        for k, v in label_counts.most_common():
            f.write(f"| `{k}` | {v} |\n")

    print(f"T2a · policy 含 tags/classification: {len(t2a)} 篇")
    print(f"T2b · commentary 缺 title:           {len(t2b)} 篇")
    print(f"T2c · commentary 含 policy-only 字段: {len(t2c)} 篇")
    print(f"\nWrote: {md}")


if __name__ == "__main__":
    main()
