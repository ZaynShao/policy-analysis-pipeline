#!/usr/bin/env python3
"""
T2b · commentary 从文件名补 title 字段

文件名格式(优先级):
  1. 【<title>】-... → 取 】 之前
  2. <title>-<domain>.md → 去掉末尾 `-xxx.com|cn|...` domain
  3. 直接用 stem(去 .md)

Frontmatter 操作:
  - 缺 title key:在 `---\n` 之后第一行插入 `title: '<extracted>'`
  - title 为空值:替换值

不动其他字段,不动 body。

输入: state/T2/t2b_commentary_missing_title.jsonl
依赖: SCHEMA §F drift 第 4 条(commentary 缺 title 数据缺陷)

用法:
    python3 scripts/_oneshot/t2b_commentary_backfill_title.py
    python3 scripts/_oneshot/t2b_commentary_backfill_title.py --show-diff
    python3 scripts/_oneshot/t2b_commentary_backfill_title.py --apply
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
INVENTORY = Path(__file__).resolve().parents[2] / "state" / "T2" / "t2b_commentary_missing_title.jsonl"
LOG = Path(__file__).resolve().parents[2] / "state" / "T2" / "t2b_apply_log.jsonl"


def extract_title(fn: str) -> str:
    stem = fn.rsplit(".md", 1)[0]
    # 1. 中文 brackets
    m = re.match(r"^【(.*?)】", stem)
    if m:
        return m.group(1).strip()
    # 2. 去掉末尾 -<domain>(domain 含 .)
    cleaned = re.sub(r"\s*-\s*[\w.-]+\.[\w.]+$", "", stem)
    # 3. 去掉末尾 .pdf 等扩展
    cleaned = re.sub(r"\.(pdf|html|htm|shtml)$", "", cleaned, flags=re.I)
    return cleaned.strip() or stem.strip()


def yaml_quote(s: str) -> str:
    """对 title 字符串做 yaml 单引号包装(单引号在 yaml 中只需 escape 为 '')。"""
    return "'" + s.replace("'", "''") + "'"


def patch_file(text: str, title: str) -> tuple[str, str]:
    """返回 (new_text, action: 'inserted'|'replaced')。"""
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    end = text.index("\n---\n", 4)
    fm = text[4:end]
    after = text[end:]  # 含 "\n---\n"

    # 是否已有 title 行?
    m = re.search(r"(?m)^title:\s*(.*)$", fm)
    quoted = yaml_quote(title)
    if m:
        # 替换
        new_fm = re.sub(r"(?m)^title:\s*.*$", f"title: {quoted}", fm, count=1)
        action = "replaced"
    else:
        # 在 fm 顶部插入
        new_fm = f"title: {quoted}\n" + fm
        action = "inserted"
    return "---\n" + new_fm + after, action


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--inventory", type=Path, default=INVENTORY)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show-diff", action="store_true")
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.inventory.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"T2b 待处理: {len(rows)} 篇")
    print(f"模式: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    com_dir = args.vault / "0_raw" / "commentaries"
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    log, errs = [], []
    ok = 0

    for idx, r in enumerate(rows):
        fp = com_dir / r["filename"]
        if not fp.exists():
            errs.append(f"{r['filename']}: 不存在")
            continue
        title = extract_title(r["filename"])
        if not title:
            errs.append(f"{r['filename']}: 抽不出 title")
            continue
        old_text = fp.read_text(encoding="utf-8")
        try:
            new_text, action = patch_file(old_text, title)
        except Exception as e:
            errs.append(f"{r['filename']}: {e}")
            continue

        if args.show_diff and idx < 3:
            print(f"--- {r['filename'][:60]}... ---")
            print(f"  extracted title: '{title}' (action: {action})")
            diff = difflib.unified_diff(
                old_text.splitlines(keepends=True)[:6],
                new_text.splitlines(keepends=True)[:6],
                fromfile=r["filename"], tofile="(after)", n=2)
            for line in diff:
                if line.startswith(("---", "+++", "@@")):
                    continue
                sys.stdout.write(line)
            print()

        if args.apply:
            fp.write_text(new_text, encoding="utf-8")
            log.append({
                "filename": r["filename"],
                "extracted_title": title,
                "action": action,
                "applied_at": now,
            })
            ok += 1
        else:
            log.append({"filename": r["filename"], "would_title": title, "action": action})

    if args.apply:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("w", encoding="utf-8") as f:
            for e in log:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"\n✓ Apply: {ok} 篇 / {len(errs)} 错")
        print(f"✓ 日志: {LOG}")
    else:
        print(f"\nDry-run: {len(log)} 篇会改 / {len(errs)} 错")
        if log:
            print("\n前 8 个抽取结果:")
            for e in log[:8]:
                print(f"  {e['would_title'][:60]}")

    if errs:
        print(f"\n⚠️ {len(errs)} 错:")
        for e in errs[:5]:
            print(f"  {e}")


if __name__ == "__main__":
    main()
