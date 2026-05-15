#!/usr/bin/env python3
"""
T2c · 删 commentary frontmatter 中的 policy-only 残留字段

适用于 `_migrated_from: policies` 的 commentary(原政策被 reclassify 为评论,
但 policy frontmatter 字段未清)。

删除以下顶级 key(及其多行值块):
  id, issuer, region, issuer_canonical, official_number, tags,
  _migrated_from, _migrated_at, _review_needed_*

不动 body,不动其他字段(title / source_url / date_published / commentary_type /
related_policy / provenance 等保留)。

输入: state/T2/t2c_commentary_policy_only_fields.jsonl
依赖: SCHEMA §F 严重违反条目 3(reclassified 残留)

用法:
    python3 scripts/_oneshot/t2c_commentary_drop_policy_fields.py
    python3 scripts/_oneshot/t2c_commentary_drop_policy_fields.py --show-diff
    python3 scripts/_oneshot/t2c_commentary_drop_policy_fields.py --apply
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import json
import re
import sys
from pathlib import Path

DEFAULT_VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
INVENTORY = Path(__file__).resolve().parents[2] / "state" / "T2" / "t2c_commentary_policy_only_fields.jsonl"
LOG = Path(__file__).resolve().parents[2] / "state" / "T2" / "t2c_apply_log.jsonl"

KEYS_EXACT = {
    "id", "issuer", "region", "issuer_canonical", "official_number", "tags",
    "_migrated_from", "_migrated_at",
}
KEYS_PREFIX = ("_review_needed",)


def remove_top_keys(fm_text: str) -> tuple[str, list[str]]:
    """删除指定 top-level keys 及其多行值块。返回 (新 text, 删除的 key 列表)。"""
    lines = fm_text.split("\n")
    out = []
    removed = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z_][\w_]*)\s*:", line)
        if m:
            key = m.group(1)
            should_remove = (key in KEYS_EXACT) or any(key.startswith(p) for p in KEYS_PREFIX)
            if should_remove:
                removed.append(key)
                i += 1
                # 吞掉后续以空格/Tab/- 开头的多行值
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.startswith((" ", "\t", "-")):
                        i += 1
                    else:
                        break
                continue
        out.append(line)
        i += 1
    return "\n".join(out), removed


def patch_file(text: str) -> tuple[str, list[str]]:
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    end = text.index("\n---\n", 4)
    fm = text[4:end]
    body = text[end + 5:]  # 含 "\n---\n" 之后
    new_fm, removed = remove_top_keys(fm)
    return "---\n" + new_fm + "\n---\n" + body, removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--inventory", type=Path, default=INVENTORY)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show-diff", action="store_true")
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.inventory.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"T2c 待处理: {len(rows)} 篇")
    print(f"模式: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    com_dir = args.vault / "0_raw" / "commentaries"
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    log = []
    ok, errs = 0, []

    for idx, r in enumerate(rows):
        fp = com_dir / r["filename"]
        if not fp.exists():
            errs.append(f"{r['filename']}: 不存在")
            continue
        old_text = fp.read_text(encoding="utf-8")
        try:
            new_text, removed = patch_file(old_text)
        except Exception as e:
            errs.append(f"{r['filename']}: {e}")
            continue

        if old_text == new_text:
            errs.append(f"{r['filename']}: no-op(可能字段已不存在)")
            continue

        if args.show_diff and idx < 2:
            print(f"--- {r['filename']} ---")
            diff = difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=r["filename"], tofile=r["filename"] + " (after)", n=2)
            for line in diff:
                if line.startswith(("---", "+++", "@@")):
                    continue
                sys.stdout.write(line)
            print(f"  · removed: {removed}\n")

        if args.apply:
            fp.write_text(new_text, encoding="utf-8")
            log.append({
                "filename": r["filename"],
                "removed_fields": removed,
                "applied_at": now,
            })
            ok += 1
        else:
            log.append({"filename": r["filename"], "would_remove": removed})

    if not args.apply:
        print(f"\nDry-run: {len(log)} 篇会改 / {len(errs)} 错")
        # 字段删除统计
        from collections import Counter
        c = Counter()
        for e in log:
            for f in e.get("would_remove", []):
                c[f] += 1
        print("\n字段删除分布:")
        for k, v in c.most_common():
            print(f"  {k}: {v}")
    else:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("w", encoding="utf-8") as f:
            for e in log:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"\n✓ Apply 完成: {ok} 篇 / {len(errs)} 错")
        print(f"✓ 日志: {LOG}")

    if errs:
        print(f"\n⚠️ 错误/跳过 ({len(errs)}):")
        for e in errs[:5]:
            print(f"  {e}")


if __name__ == "__main__":
    main()
