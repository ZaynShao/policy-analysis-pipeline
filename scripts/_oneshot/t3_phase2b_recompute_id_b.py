#!/usr/bin/env python3
"""
T3 Phase 2b · B 类(date 是 placeholder)的 date 重抽 + id 重算

抽取优先级:
  1. URL 含 `t(YYYY)(MM)(DD)` 精确日 → 用之
  2. URL 含 `/(YYYY)(MM)/` 年月  → 用 YYYY-MM-01(改进 placeholder)
  3. URL 含 `/(YYYY)-(MM)/` 年月 → 用 YYYY-MM-01
  4. Body 含 "发布时间[:]YYYY[-/年.]MM[-/月.]DD" → 用之
  5. Body 含 "YYYY年MM月DD日" → 用之
  6. URL 仅含年份 → 若现 date 年份一致,不改 date 仅改 id;若不一致用 YYYY-01-01
  7. 全部失败 → 跳过,留 backlog

每篇:
  - 若 date 改 → 写 provenance.date_fixed_at / date_fixed_method / date_fixed_from
  - 若 id 改 → 写 provenance.id_fixed_at / id_fixed_method / id_fixed_from
  - aliases 加旧 id(保留 Obsidian 反链)

不动 body,不动 issuer,不动 region。

依赖:SCHEMA v1.1(身份字段重算白名单)+ Phase 2a 风格 patch_frontmatter

用法:
    python3 scripts/_oneshot/t3_phase2b_recompute_id_b.py             # dry-run
    python3 scripts/_oneshot/t3_phase2b_recompute_id_b.py --show-diff
    python3 scripts/_oneshot/t3_phase2b_recompute_id_b.py --apply
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
LOG_PATH = Path(__file__).resolve().parents[2] / "state" / "T3" / "phase2b_date_id_recompute_log.jsonl"

OLD_ID_RE = re.compile(r"^P_1900_(?P<issuer>[^_]+)_(?P<hash>.+)$")


# ---------- date extractors ----------
def extract_from_url(url: str) -> tuple[str | None, str]:
    """返回 (YYYY-MM-DD, method)。失败返回 (None, '')。"""
    if not url:
        return None, ""
    # 1. /202405/t20240520_xxx
    m = re.search(r"/t(20\d{2})(\d{2})(\d{2})", url)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime.date(y, mo, d).isoformat(), "url_path_pattern"
        except ValueError:
            pass
    # 2. /YYYYMM/
    m = re.search(r"/(20\d{2})(\d{2})/", url)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y}-{mo:02d}-01", "url_path_month_only"
    # 3. /YYYY-MM/
    m = re.search(r"/(20\d{2})-(\d{2})/", url)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y}-{mo:02d}-01", "url_path_month_only"
    # 4. URL 仅含 YYYY
    m = re.search(r"(20\d{2})", url)
    if m:
        return f"{m.group(1)}-01-01", "url_year_only"
    return None, ""


def extract_from_body(body: str) -> tuple[str | None, str]:
    if not body:
        return None, ""
    head = body[:3000]
    # 1. 发布时间:YYYY-MM-DD / YYYY/MM/DD
    m = re.search(r"发布时间[:：]\s*(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})", head)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime.date(y, mo, d).isoformat(), "body_publish_time"
        except ValueError:
            pass
    # 2. YYYY年M月D日
    m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", head)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime.date(y, mo, d).isoformat(), "body_chinese_date"
        except ValueError:
            pass
    return None, ""


def body_of(text: str) -> str:
    if text.startswith("---\n"):
        try:
            end = text.index("\n---\n", 4)
            return text[end + 5:]
        except ValueError:
            pass
    return text


# ---------- patch frontmatter ----------
def patch_frontmatter(text: str, old_id: str, new_id: str, old_date: str,
                       new_date: str | None, date_method: str | None,
                       now_iso: str) -> tuple[str, list[str]]:
    notes = []
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    end = text.index("\n---\n", 4)
    fm = text[:end + 1]
    body = text[end + 1:]

    # 1. id
    new_fm, n = re.subn(r"(?m)^id:\s*'?" + re.escape(old_id) + r"'?\s*$",
                        f"id: {new_id}", fm)
    if n != 1:
        raise ValueError(f"id 行匹配失败: 期望 1 次实际 {n}")
    notes.append(f"id: {old_id} → {new_id}")

    # 2. aliases
    alias_pat = re.compile(r"(?m)^aliases:\s*\n((?:[ \t]*-\s*[^\n]+\n)+)")
    am = alias_pat.search(new_fm)
    if not am:
        raise ValueError("aliases 段未找到")
    alias_block = am.group(1)
    alias_block_new, _ = re.subn(
        r"-\s*'?" + re.escape(old_id) + r"'?",
        f"- {new_id}", alias_block, count=1)
    if not alias_block_new.endswith("\n"):
        alias_block_new += "\n"
    alias_block_new += f"- {old_id}\n"
    new_fm = new_fm[:am.start(1)] + alias_block_new + new_fm[am.end(1):]
    notes.append(f"aliases: 首项 → {new_id};追加旧 id {old_id}")

    # 3. date(若需改)
    if new_date and new_date != old_date:
        new_fm, n = re.subn(
            r"(?m)^date:\s*'?" + re.escape(str(old_date)) + r"'?\s*$",
            f"date: '{new_date}'", new_fm
        )
        if n != 1:
            # 也许 date 是 null / 空
            new_fm2, n2 = re.subn(r"(?m)^date:\s*('?'?\s*)$",
                                   f"date: '{new_date}'", new_fm)
            if n2 == 1:
                new_fm = new_fm2
            else:
                raise ValueError(f"date 行匹配失败: 期望 1 次")
        notes.append(f"date: {old_date} → {new_date} ({date_method})")

    # 4. provenance 追加
    prov_match = re.search(r"(?m)^provenance:\s*\n", new_fm)
    if not prov_match:
        raise ValueError("provenance 段未找到")
    pos = prov_match.end()
    sub_end = pos
    while sub_end < len(new_fm):
        nl = new_fm.find("\n", sub_end)
        if nl == -1:
            break
        line = new_fm[sub_end:nl + 1]
        if re.match(r"^[ \t]+\S", line) or line.strip() == "":
            sub_end = nl + 1
        else:
            break

    added_lines = []
    if new_date and new_date != old_date:
        added_lines += [
            f"  date_fixed_at: '{now_iso}'",
            f"  date_fixed_method: {date_method}",
            f"  date_fixed_from: '{old_date}'",
        ]
    added_lines += [
        f"  id_fixed_at: '{now_iso}'",
        f"  id_fixed_method: id_recompute_from_metadata",
        f"  id_fixed_from: {old_id}",
    ]
    added = "\n".join(added_lines) + "\n"
    new_fm = new_fm[:sub_end] + added + new_fm[sub_end:]
    notes.append(f"provenance: 追加 {len(added_lines)} 行审计")

    return new_fm + body, notes


# ---------- main ----------
def scan_existing_ids(policies_dir: Path) -> set[str]:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--inventory", type=Path, default=INVENTORY_DEFAULT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show-diff", action="store_true")
    args = ap.parse_args()

    rows = [r for r in [json.loads(l) for l in args.inventory.read_text(encoding="utf-8").splitlines() if l.strip()] if r.get("is_b") and not r.get("is_a")]
    print(f"B 类待处理: {len(rows)} 篇")

    policies_dir = args.vault / "0_raw" / "policies"
    print("扫描现存 id...")
    existing = scan_existing_ids(policies_dir)
    print(f"现存 id: {len(existing)}")
    print(f"模式: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    now_iso = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    plans, skipped = [], []
    method_counts = {}

    for r in rows:
        fp = policies_dir / r["filename"]
        if not fp.exists():
            skipped.append((r["filename"], "源文件不存在"))
            continue
        text = fp.read_text(encoding="utf-8")
        body = body_of(text)

        # 抽 date
        new_date, method = extract_from_url(r.get("url", ""))
        if not new_date:
            new_date, method = extract_from_body(body)

        cur_date = str(r["date"])

        # 决策:date 是否要改?
        # 若没抽到,但现 date 已有合理年份 → 不改 date,仅改 id
        # 若抽到了:
        #   - 精确日(url_path_pattern / body_*):有 → 用,即使年与现 date 同
        #   - month_only / year_only:仅当现 date 是 placeholder 且抽到的更具体时改
        will_change_date = False
        if new_date:
            if method in ("url_path_pattern", "body_publish_time", "body_chinese_date"):
                will_change_date = (new_date != cur_date)
            elif method == "url_path_month_only":
                # 现 date 是 jan_1 或 == fetched 同日,改为 YYYY-MM-01
                will_change_date = (new_date != cur_date)
            elif method == "url_year_only":
                # 只抽到年:若现 date 年份不同才改;若一致不改 date
                cur_year = cur_date[:4] if cur_date else ""
                new_year = new_date[:4]
                will_change_date = (cur_year != new_year)

        # 用哪个 date 算 id?
        effective_date = new_date if will_change_date else cur_date
        try:
            year = datetime.date.fromisoformat(effective_date).year
        except Exception:
            skipped.append((r["filename"], f"date 不可解析: {effective_date}"))
            continue

        m = OLD_ID_RE.match(r["id"])
        if not m:
            skipped.append((r["filename"], f"id 格式异常: {r['id']}"))
            continue
        new_id = f"P_{year}_{m.group('issuer')}_{m.group('hash')}"

        if new_id == r["id"] and not will_change_date:
            # 既不改 date 又不改 id → 实际是 no-op,跳过
            skipped.append((r["filename"], "no-op:新 id 与旧 id 同且 date 不改"))
            continue

        if new_id in existing and new_id != r["id"]:
            skipped.append((r["filename"], f"id 碰撞: {new_id}"))
            continue

        plans.append({
            "filename": r["filename"],
            "old_id": r["id"],
            "new_id": new_id,
            "old_date": cur_date,
            "new_date": new_date if will_change_date else None,
            "date_method": method if will_change_date else None,
        })
        existing.add(new_id)
        method_counts[method or "(no_change)"] = method_counts.get(method or "(no_change)", 0) + 1

    print(f"可处理: {len(plans)} 篇")
    print(f"跳过: {len(skipped)} 篇")
    print(f"\nDate 抽取方法分布:")
    for k, v in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print()

    if skipped:
        print("跳过原因(前 10):")
        for fn, reason in skipped[:10]:
            print(f"  {fn[:50]}... -- {reason}")
        print()

    print("前 10 plan:")
    for p in plans[:10]:
        d_part = f", date {p['old_date']} → {p['new_date']} ({p['date_method']})" if p['new_date'] else ", date 不变"
        print(f"  {p['old_id']} → {p['new_id']}{d_part}")
    print()

    if args.show_diff:
        print("=" * 70)
        print("Diff 预览(前 3 篇)")
        print("=" * 70)
        for p in plans[:3]:
            fp = policies_dir / p["filename"]
            old_text = fp.read_text(encoding="utf-8")
            try:
                new_text, notes = patch_frontmatter(
                    old_text, p["old_id"], p["new_id"], p["old_date"],
                    p["new_date"], p["date_method"], now_iso)
            except Exception as e:
                print(f"❌ {p['filename']}: {e}")
                continue
            diff = difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=p["filename"], tofile=p["filename"] + " (after)", n=2)
            print(f"\n--- {p['filename']} ---")
            for line in diff:
                if line.startswith(("---", "+++", "@@")):
                    continue
                sys.stdout.write(line)
            for nt in notes:
                print(f"  · {nt}")

    if args.apply:
        log = []
        ok, errs = 0, []
        for p in plans:
            fp = policies_dir / p["filename"]
            old_text = fp.read_text(encoding="utf-8")
            try:
                new_text, _ = patch_frontmatter(
                    old_text, p["old_id"], p["new_id"], p["old_date"],
                    p["new_date"], p["date_method"], now_iso)
            except Exception as e:
                errs.append(f"{p['filename']}: {e}")
                continue
            fp.write_text(new_text, encoding="utf-8")
            log.append({**p, "applied_at": now_iso})
            ok += 1
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("w", encoding="utf-8") as f:
            for e in log:
                f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        print(f"✓ Apply: {ok} 篇 / 错 {len(errs)} 篇")
        print(f"✓ 日志: {LOG_PATH}")
        if errs:
            for e in errs:
                print(f"   ❌ {e}")
    else:
        print("dry-run 完成。--show-diff 看 diff,--apply 真跑。")


if __name__ == "__main__":
    main()
