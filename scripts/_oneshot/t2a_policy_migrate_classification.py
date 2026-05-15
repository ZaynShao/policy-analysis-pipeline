#!/usr/bin/env python3
"""
T2a · policy 迁出 tags + classification 到派生层

51 篇 policy raw frontmatter 含 `tags: [classified_main_graph_exclude]` +
`classification: {isolated_label, suggested_action, confidence, classified_at, classified_by}`,
这是 B7 isolated_classification 任务 LLM 派生倒灌 raw(违反 LESSONS A2/A3)。

操作:
  1. 解析每篇 frontmatter,抽 classification block + tags
  2. 追加一行 JSON 到新派生层 `1_extracted/policy_classification.jsonl`
  3. 从 raw 删除顶级 `tags` 和 `classification` 字段
  4. 从 raw `provenance` 子键删 `classification_applied_at`(同流程产物)

不动 body,其他字段保留。

输入: state/T2/t2a_policy_tags_classification.jsonl

用法:
    python3 scripts/_oneshot/t2a_policy_migrate_classification.py
    python3 scripts/_oneshot/t2a_policy_migrate_classification.py --show-diff
    python3 scripts/_oneshot/t2a_policy_migrate_classification.py --apply
"""
from __future__ import annotations

import argparse
import datetime
import difflib
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
INVENTORY = Path(__file__).resolve().parents[2] / "state" / "T2" / "t2a_policy_tags_classification.jsonl"
LOG = Path(__file__).resolve().parents[2] / "state" / "T2" / "t2a_apply_log.jsonl"
DERIVED_TARGET = "1_extracted/policy_classification.jsonl"


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


def remove_top_level_keys(fm_text: str, keys: set[str]) -> str:
    lines = fm_text.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z_][\w_]*)\s*:", line)
        if m and m.group(1) in keys:
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt.startswith((" ", "\t", "-")):
                    i += 1
                else:
                    break
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def remove_provenance_subkey(fm_text: str, subkey: str) -> str:
    """从 provenance 块内删一个子键(2 空格缩进)。"""
    pat = re.compile(r"(?m)^  " + re.escape(subkey) + r":\s*[^\n]*\n")
    return pat.sub("", fm_text)


def _json_default(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    return str(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--inventory", type=Path, default=INVENTORY)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show-diff", action="store_true")
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.inventory.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"T2a 待处理: {len(rows)} 篇")
    print(f"模式: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    pol_dir = args.vault / "0_raw" / "policies"
    derived_path = args.vault / DERIVED_TARGET
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    derived_records, log, errs = [], [], []

    for idx, r in enumerate(rows):
        fp = pol_dir / r["filename"]
        if not fp.exists():
            errs.append(f"{r['filename']}: 不存在")
            continue
        old_text = fp.read_text(encoding="utf-8")
        fm = parse_fm(old_text)
        if not isinstance(fm, dict):
            errs.append(f"{r['filename']}: fm 解析失败")
            continue

        pid = fm.get("id", "")
        cls = fm.get("classification") or {}
        tags = fm.get("tags") or []
        prov = fm.get("provenance") or {}
        applied_at = prov.get("classification_applied_at")

        record = {
            "policy_id": pid,
            "isolated_label": cls.get("isolated_label"),
            "suggested_action": cls.get("suggested_action"),
            "confidence": cls.get("confidence"),
            "classified_at": cls.get("classified_at"),
            "classified_by": cls.get("classified_by"),
            "tags": tags,
            "applied_to_raw_at": applied_at,
            "migrated_to_derived_at": now,
            "source": "policy_raw_frontmatter_pre_t2a_migration",
        }
        derived_records.append(record)

        # patch raw
        end = old_text.index("\n---\n", 4)
        fm_text = old_text[4:end]
        body = old_text[end:]
        new_fm = remove_top_level_keys(fm_text, {"tags", "classification"})
        new_fm = remove_provenance_subkey(new_fm, "classification_applied_at")
        new_text = "---\n" + new_fm + body

        if args.show_diff and idx < 2:
            print(f"--- {r['filename'][:60]}... ---")
            diff = difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=r["filename"], tofile="(after)", n=1)
            for line in diff:
                if line.startswith(("---", "+++", "@@")):
                    continue
                sys.stdout.write(line)
            print()

        if args.apply:
            fp.write_text(new_text, encoding="utf-8")
            log.append({"filename": r["filename"], "pid": pid, "applied_at": now})
        else:
            log.append({"filename": r["filename"], "pid": pid})

    # 写派生层 + 日志
    if args.apply:
        derived_path.parent.mkdir(parents=True, exist_ok=True)
        with derived_path.open("a", encoding="utf-8") as f:
            for rec in derived_records:
                f.write(json.dumps(rec, ensure_ascii=False, default=_json_default) + "\n")
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("w", encoding="utf-8") as f:
            for e in log:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"\n✓ Apply: {len(log)} 篇 / {len(errs)} 错")
        print(f"✓ 派生层: {derived_path} (追加 {len(derived_records)} 行)")
        print(f"✓ 日志: {LOG}")
    else:
        # 也输出预览派生层
        preview_path = LOG.parent / "t2a_dryrun_derived_preview.jsonl"
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with preview_path.open("w", encoding="utf-8") as f:
            for rec in derived_records:
                f.write(json.dumps(rec, ensure_ascii=False, default=_json_default) + "\n")
        print(f"\nDry-run: {len(derived_records)} 条派生记录会写到 {DERIVED_TARGET}")
        print(f"预览: {preview_path}")
        # label 分布
        from collections import Counter
        c = Counter(r["isolated_label"] for r in derived_records)
        print(f"\nisolated_label 分布:")
        for k, v in c.most_common():
            print(f"  {k}: {v}")

    if errs:
        print(f"\n⚠️ {len(errs)} 错:")
        for e in errs[:5]:
            print(f"  {e}")


if __name__ == "__main__":
    main()
