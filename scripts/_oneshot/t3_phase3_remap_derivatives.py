#!/usr/bin/env python3
"""
T3 Phase 3 · 派生层重指 + 孤儿派生归档

输入:
  - state/T3/p1900_inventory.jsonl(B/C 类的 id 重算映射)
  - state/T3/t3_a1_classifier_drops_2026-05-08_log.jsonl(A 类 archive 列表)

操作:
  ① A 类 28 个 archived 政策的 P_1900 派生(business_view yaml / summaries 行 / relations from-to / themes 引用):
      - business_view yaml → archive 到 `_meta/business_view/_archive/`
      - policy_summaries.jsonl → 删除对应行(归档到 `1_extracted/_archive/policy_summaries_t3_drops.jsonl`)
      - relations jsonl → 删除任何 from/to 涉及 archived id 的行(归档同上)
      - themes markdown 中 `[[P_1900_*]]` 引用 archived id → **不动**(人类阅读层,aliases 保留)
  ② B/C 类的 id 重指(从旧 P_1900_* → 新 P_<year>_*):
      - business_view yaml 文件名 rename + 内部 pid 字段改
      - policy_summaries.jsonl 内 policy_id 改
      - relations 7 类 jsonl 内 from/to 改
      - themes markdown 中链接 **不动**(aliases 兜底,不破坏上下文)

dry-run 默认。

用法:
    python3 scripts/_oneshot/t3_phase3_remap_derivatives.py
    python3 scripts/_oneshot/t3_phase3_remap_derivatives.py --apply
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# 复用 Phase 2b 的 extractors
from t3_phase2b_recompute_id_b import extract_from_url, extract_from_body, body_of, OLD_ID_RE

DEFAULT_VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
STATE_DIR = Path(__file__).resolve().parents[2] / "state" / "T3"
INVENTORY = STATE_DIR / "p1900_inventory.jsonl"
ARCHIVE_LOG = STATE_DIR / "t3_a1_classifier_drops_2026-05-08_log.jsonl"
LOG_OUT = STATE_DIR / "phase3_remap_log.json"


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def compute_b_mapping(vault: Path, rows: list[dict]) -> dict[str, str]:
    """对 B 类 inventory 行算 old_id → new_id 映射(沿用 Phase 2b 逻辑)。"""
    mapping = {}
    for r in rows:
        if not r.get("is_b") or r.get("is_a"):
            continue
        fp = vault / "0_raw" / "policies" / r["filename"]
        if not fp.exists():
            continue
        text = fp.read_text(encoding="utf-8")
        body = body_of(text)
        new_date, method = extract_from_url(r.get("url", ""))
        if not new_date:
            new_date, method = extract_from_body(body)
        cur_date = str(r["date"])
        will_change = False
        if new_date:
            if method in ("url_path_pattern", "body_publish_time", "body_chinese_date"):
                will_change = new_date != cur_date
            elif method == "url_path_month_only":
                will_change = new_date != cur_date
            elif method == "url_year_only":
                cy = cur_date[:4] if cur_date else ""
                will_change = cy != new_date[:4]
        effective = new_date if will_change else cur_date
        try:
            y = datetime.date.fromisoformat(effective).year
        except Exception:
            continue
        m = OLD_ID_RE.match(r["id"])
        if not m:
            continue
        new_id = f"P_{y}_{m.group('issuer')}_{m.group('hash')}"
        if new_id != r["id"]:
            mapping[r["id"]] = new_id
    return mapping


def compute_c_mapping(rows: list[dict]) -> dict[str, str]:
    """C 类:date OK,直接算 year_from_date。"""
    mapping = {}
    for r in rows:
        if not r.get("is_c") or r.get("is_a"):
            continue
        m = OLD_ID_RE.match(r["id"])
        if not m:
            continue
        try:
            y = datetime.date.fromisoformat(str(r["date"])).year
        except Exception:
            continue
        new_id = f"P_{y}_{m.group('issuer')}_{m.group('hash')}"
        if new_id != r["id"]:
            mapping[r["id"]] = new_id
    return mapping


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    inv = load_jsonl(INVENTORY)
    arch = load_jsonl(ARCHIVE_LOG)

    archived_ids = {e["id"] for e in arch}
    print(f"已 archive 的 P_1900 id: {len(archived_ids)} 个")

    b_map = compute_b_mapping(args.vault, inv)
    c_map = compute_c_mapping(inv)
    remap = {**b_map, **c_map}
    print(f"B 类 remap: {len(b_map)},C 类 remap: {len(c_map)},合计 remap: {len(remap)}")
    print(f"模式: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    actions = {
        "business_view_rename": [],
        "business_view_archive": [],
        "summaries_jsonl_remap": 0,
        "summaries_jsonl_archive": 0,
        "relations_remap": {},
        "relations_archive": {},
    }

    # 1. business_view yaml
    bv_dir = args.vault / "_meta" / "business_view"
    bv_archive_dir = bv_dir / "_archive"
    for f in bv_dir.iterdir():
        if not f.is_file() or not f.name.endswith(".yaml"):
            continue
        pid = f.stem
        if pid in archived_ids:
            actions["business_view_archive"].append(f.name)
        elif pid in remap:
            actions["business_view_rename"].append((f.name, remap[pid] + ".yaml"))

    # 2. policy_summaries.jsonl
    sum_path = args.vault / "1_extracted" / "policy_summaries.jsonl"
    sum_lines_keep, sum_lines_archive = [], []
    if sum_path.exists():
        for line in sum_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                sum_lines_keep.append(line)
                continue
            pid = obj.get("policy_id") or obj.get("pid") or ""
            if pid in archived_ids:
                actions["summaries_jsonl_archive"] += 1
                sum_lines_archive.append(line)
            elif pid in remap:
                if "policy_id" in obj:
                    obj["policy_id"] = remap[pid]
                if "pid" in obj:
                    obj["pid"] = remap[pid]
                actions["summaries_jsonl_remap"] += 1
                sum_lines_keep.append(json.dumps(obj, ensure_ascii=False))
            else:
                sum_lines_keep.append(line)

    # 3. relations
    rel_dir = args.vault / "1_extracted" / "relations"
    rel_changes = {}  # rel -> (keep_lines, archive_lines, remapped_count, archived_count)
    for rf in rel_dir.glob("*.jsonl"):
        keeps, archs = [], []
        rmp, arc = 0, 0
        for line in rf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                keeps.append(line)
                continue
            f_id, t_id = obj.get("from"), obj.get("to")
            if f_id in archived_ids or t_id in archived_ids:
                arc += 1
                archs.append(line)
                continue
            changed = False
            if f_id in remap:
                obj["from"] = remap[f_id]
                changed = True
            if t_id in remap:
                obj["to"] = remap[t_id]
                changed = True
            if changed:
                rmp += 1
                keeps.append(json.dumps(obj, ensure_ascii=False))
            else:
                keeps.append(line)
        rel_changes[rf.name] = (keeps, archs, rmp, arc)
        actions["relations_remap"][rf.name] = rmp
        actions["relations_archive"][rf.name] = arc

    # ---------- 报告 ----------
    print("==== Business view yaml ====")
    print(f"  rename: {len(actions['business_view_rename'])}")
    for a, b in actions["business_view_rename"][:5]:
        print(f"    {a}  →  {b}")
    if len(actions['business_view_rename']) > 5:
        print(f"    ... 还有 {len(actions['business_view_rename']) - 5}")
    print(f"  archive: {len(actions['business_view_archive'])}")
    for f in actions["business_view_archive"][:5]:
        print(f"    {f}")
    if len(actions['business_view_archive']) > 5:
        print(f"    ... 还有 {len(actions['business_view_archive']) - 5}")

    print(f"\n==== policy_summaries.jsonl ====")
    print(f"  remap: {actions['summaries_jsonl_remap']} 行")
    print(f"  archive: {actions['summaries_jsonl_archive']} 行")

    print(f"\n==== relations ====")
    for name, (keeps, archs, rmp, arc) in rel_changes.items():
        if rmp or arc:
            print(f"  {name}: remap {rmp},archive {arc}")

    # ---------- APPLY ----------
    if not args.apply:
        print("\ndry-run 完成。--apply 真跑。")
        return

    print("\nApplying...")
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    bv_archive_dir.mkdir(parents=True, exist_ok=True)

    # business_view archive
    for fn in actions["business_view_archive"]:
        src = bv_dir / fn
        dst = bv_archive_dir / fn
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))

    # business_view rename + pid 字段改
    for old_name, new_name in actions["business_view_rename"]:
        src = bv_dir / old_name
        dst = bv_dir / new_name
        if src.exists() and not dst.exists():
            txt = src.read_text(encoding="utf-8")
            old_pid = old_name[:-5]
            new_pid = new_name[:-5]
            txt = re.sub(r"^pid:\s*\S+", f"pid: {new_pid}", txt, count=1, flags=re.M)
            dst.write_text(txt, encoding="utf-8")
            src.unlink()

    # policy_summaries.jsonl
    if sum_path.exists():
        sum_archive_path = args.vault / "1_extracted" / "_archive" / "policy_summaries_t3_drops.jsonl"
        sum_archive_path.parent.mkdir(parents=True, exist_ok=True)
        if sum_lines_archive:
            with sum_archive_path.open("a", encoding="utf-8") as f:
                for l in sum_lines_archive:
                    f.write(l + "\n")
        sum_path.write_text("\n".join(sum_lines_keep) + "\n", encoding="utf-8")

    # relations
    rel_archive_dir = args.vault / "1_extracted" / "_archive" / "relations_t3_drops"
    rel_archive_dir.mkdir(parents=True, exist_ok=True)
    for name, (keeps, archs, rmp, arc) in rel_changes.items():
        if not (rmp or arc):
            continue
        rf = rel_dir / name
        if archs:
            with (rel_archive_dir / name).open("a", encoding="utf-8") as f:
                for l in archs:
                    f.write(l + "\n")
        rf.write_text("\n".join(keeps) + "\n", encoding="utf-8")

    # 写最终日志
    LOG_OUT.write_text(json.dumps({
        "applied_at": now,
        "remap_count": len(remap),
        "archived_count": len(archived_ids),
        "actions": actions,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"✓ 完成。日志: {LOG_OUT}")


if __name__ == "__main__":
    main()
