#!/usr/bin/env python3
"""
T3 Phase 2a · C 类(date OK,只 id 漂)的 id 重算

对 inventory 里 is_c=true 的政策:
  - 旧 id: P_1900_<issuer_short>_<hash>
  - 新 id: P_<date.year>_<issuer_short>_<hash>
  - aliases 数组保留旧 id(Obsidian 反链兼容)
  - provenance 添加 id_fixed_at / id_fixed_method / id_fixed_from

不动 body,不动 date,不动 issuer,不动 region。仅 id / aliases / provenance 子键。

最小 diff 模式:用正则定位行,不做 yaml round-trip,保留原缩进与引号风格。

依赖:SCHEMA v1.1(§C 新增 "Deterministic 身份字段重算" 白名单)
  → SCHEMA 合并前 dry-run 可跑,apply 前确认 SCHEMA 已合并

用法:
    python3 scripts/_oneshot/t3_phase2a_recompute_id_c.py            # dry-run
    python3 scripts/_oneshot/t3_phase2a_recompute_id_c.py --apply
    python3 scripts/_oneshot/t3_phase2a_recompute_id_c.py --show-diff  # dry-run + 完整 diff
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
INVENTORY_DEFAULT = Path(__file__).resolve().parents[2] / "state" / "T3" / "p1900_inventory.jsonl"
LOG_PATH = Path(__file__).resolve().parents[2] / "state" / "T3" / "phase2a_id_recompute_log.jsonl"

OLD_ID_RE = re.compile(r"^P_1900_(?P<issuer>[^_]+)_(?P<hash>.+)$")


def load_inventory(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def scan_existing_ids(policies_dir: Path) -> set[str]:
    """扫整个 0_raw/policies/ 现存 frontmatter id,用于碰撞检测。"""
    ids = set()
    for p in policies_dir.iterdir():
        if not p.suffix == ".md":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        m = re.search(r"^id:\s*(\S+)", text[:1500], re.M)
        if m:
            ids.add(m.group(1).strip().strip("'\""))
    return ids


def compute_new_id(old_id: str, date_str: str) -> str | None:
    m = OLD_ID_RE.match(old_id)
    if not m:
        return None
    try:
        dt = datetime.date.fromisoformat(str(date_str))
    except Exception:
        return None
    return f"P_{dt.year}_{m.group('issuer')}_{m.group('hash')}"


def patch_frontmatter(text: str, old_id: str, new_id: str, now_iso: str) -> tuple[str, list[str]]:
    """
    最小 diff frontmatter 改写:
      1. `id: P_1900_*` → `id: P_<year>_*`
      2. aliases 列表:首项 `- P_1900_*` 改为 `- P_<year>_*`,然后下方追加 `- P_1900_*`(保留旧 id)
      3. provenance 块内追加 id_fixed_at / id_fixed_method / id_fixed_from

    返回 (新 text, 备注 list)。备注 list 解释做了什么。
    """
    notes = []
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    end = text.index("\n---\n", 4)
    fm = text[:end + 1]  # 含末行 \n,不含 ---
    body = text[end + 1:]

    # 1. id 行
    new_fm, n = re.subn(r"(?m)^id:\s*'?" + re.escape(old_id) + r"'?\s*$",
                        f"id: {new_id}", fm)
    if n != 1:
        raise ValueError(f"id 行匹配失败:期望 1 次,实际 {n}")
    notes.append(f"id: {old_id} → {new_id}")

    # 2. aliases 首项替换 + 末尾追加旧 id
    # 找 aliases: 段(直至下一个 top-level key,即 ^[a-z_]+: 在缩进 0 列)
    alias_pat = re.compile(
        r"(?m)^aliases:\s*\n((?:[ \t]*-\s*[^\n]+\n)+)"
    )
    am = alias_pat.search(new_fm)
    if not am:
        raise ValueError("aliases 段未找到")
    alias_block = am.group(1)
    # 用 new_id 替换第一处 old_id(若有),然后在末尾追加 old_id
    alias_block_new, replaced = re.subn(
        r"-\s*'?" + re.escape(old_id) + r"'?",
        f"- {new_id}",
        alias_block, count=1
    )
    # 追加旧 id 一行(保留 obsidian 反链)
    if not alias_block_new.endswith("\n"):
        alias_block_new += "\n"
    alias_block_new += f"- {old_id}\n"
    new_fm = new_fm[:am.start(1)] + alias_block_new + new_fm[am.end(1):]
    notes.append(f"aliases: 首项 {old_id} → {new_id};末尾追加 {old_id}(保留旧链接)")

    # 3. provenance 块追加 3 行
    # 找 `provenance:` 行,然后找它的子块结束(下一个顶级 key 或 ---)
    prov_match = re.search(r"(?m)^provenance:\s*\n", new_fm)
    if not prov_match:
        raise ValueError("provenance 段未找到")
    # provenance 子块:从 prov_match 末尾开始,所有以两空格缩进的行
    pos = prov_match.end()
    sub_lines_end = pos
    while sub_lines_end < len(new_fm):
        nl = new_fm.find("\n", sub_lines_end)
        if nl == -1:
            break
        line = new_fm[sub_lines_end:nl + 1]
        if re.match(r"^[ \t]+\S", line) or line.strip() == "":
            sub_lines_end = nl + 1
        else:
            break
    added = (
        f"  id_fixed_at: '{now_iso}'\n"
        f"  id_fixed_method: id_recompute_from_metadata\n"
        f"  id_fixed_from: {old_id}\n"
    )
    new_fm = new_fm[:sub_lines_end] + added + new_fm[sub_lines_end:]
    notes.append("provenance: 追加 id_fixed_at / id_fixed_method / id_fixed_from")

    return new_fm + body, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--inventory", type=Path, default=INVENTORY_DEFAULT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show-diff", action="store_true",
                    help="dry-run 模式下显示前 3 篇的完整 diff")
    args = ap.parse_args()

    rows = load_inventory(args.inventory)
    c_rows = [r for r in rows if r.get("is_c") and not r.get("is_a")]
    print(f"C 类待处理: {len(c_rows)} 篇")

    policies_dir = args.vault / "0_raw" / "policies"
    print("扫描现存 id 做碰撞检测...")
    existing_ids = scan_existing_ids(policies_dir)
    print(f"现存 id: {len(existing_ids)} 个")
    print(f"模式: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    now_iso = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    plans = []
    errors = []
    for r in c_rows:
        old_id = r["id"]
        new_id = compute_new_id(old_id, r["date"])
        if not new_id:
            errors.append(f"{r['filename']}: 无法算新 id (old={old_id}, date={r['date']})")
            continue
        if new_id in existing_ids:
            errors.append(f"{r['filename']}: 新 id {new_id} 已存在,需要 hash 加 _a 后缀(本脚本暂不处理,需人工)")
            continue
        plans.append({
            "filename": r["filename"],
            "old_id": old_id,
            "new_id": new_id,
            "date": r["date"],
        })
        existing_ids.add(new_id)

    print(f"可处理: {len(plans)} 篇")
    if errors:
        print(f"⚠️  跳过: {len(errors)} 篇")
        for e in errors[:5]:
            print(f"    {e}")
        print()

    # 预览前 10 条 plan
    print("前 10 条 plan:")
    for p in plans[:10]:
        print(f"  {p['old_id']} → {p['new_id']}  ({p['date']})")
    if len(plans) > 10:
        print(f"  ... 还有 {len(plans) - 10} 条")
    print()

    if args.show_diff:
        print("=" * 70)
        print("Diff 预览(前 3 篇)")
        print("=" * 70)
        for p in plans[:3]:
            fp = policies_dir / p["filename"]
            old_text = fp.read_text(encoding="utf-8")
            new_text, notes = patch_frontmatter(old_text, p["old_id"], p["new_id"], now_iso)
            diff = difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=p["filename"], tofile=p["filename"] + " (after)",
                n=2,
            )
            print(f"\n--- {p['filename']} ---")
            for line in diff:
                if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                    continue
                sys.stdout.write(line)
            print()
            for nt in notes:
                print(f"  · {nt}")

    if args.apply:
        log = []
        ok = 0
        for p in plans:
            fp = policies_dir / p["filename"]
            old_text = fp.read_text(encoding="utf-8")
            try:
                new_text, notes = patch_frontmatter(old_text, p["old_id"], p["new_id"], now_iso)
            except Exception as e:
                errors.append(f"{p['filename']}: patch 失败 {e}")
                continue
            fp.write_text(new_text, encoding="utf-8")
            log.append({
                "filename": p["filename"],
                "old_id": p["old_id"],
                "new_id": p["new_id"],
                "applied_at": now_iso,
            })
            ok += 1
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("w", encoding="utf-8") as f:
            for e in log:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"✓ Apply 完成: {ok} 篇 / 错误 {len(errors)} 篇")
        print(f"✓ 日志: {LOG_PATH}")
        if errors:
            print("⚠️ Errors:")
            for e in errors:
                print(f"   {e}")
    else:
        print("dry-run 完成。--show-diff 看完整 diff,--apply 真跑。")


if __name__ == "__main__":
    main()
