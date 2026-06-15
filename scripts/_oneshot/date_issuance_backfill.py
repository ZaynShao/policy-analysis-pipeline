#!/usr/bin/env python3
"""存量 raw 的"发文日误标"回填(date/id 再解析)。一次性 oneshot。

复用已合并的单一真相源 scripts/l1_collect/cn_dates(不另写日期正则)。

口径(用户拍板:保守自动修 + 其余入队):
- 自动修 date,仅当 cur_date "可证为错"——生效/截止误标、未来年、或破损/占位——
  且 pick_issuance_date(全文)抽到可信落款发文日。
- 错但抽不到落款 → 入队人工。
- 合理且非误标的 date(即便与落款不同)→ 不动(信任,误伤≈零)。
- date 年份变 → 重算 id(旧 id 入 aliases);否则只改 date。§C 审计字段写 provenance。
- official_number 不在 §C 白名单 → 只在报告标记待复核,不写 raw。

用法:
    python3 scripts/_oneshot/date_issuance_backfill.py --vault "<vault>"             # dry-run + HTML 报告
    python3 scripts/_oneshot/date_issuance_backfill.py --vault "<vault>" --show-diff
    python3 scripts/_oneshot/date_issuance_backfill.py --vault "<vault>" --apply     # 写 raw(commit/push 经 produce_and_push 由操作者)
"""
from __future__ import annotations
import argparse
import datetime
import difflib
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.l1_collect.cn_dates import (
    pick_luokuan_strict, is_effective_or_deadline_date, appears_as_issuance,
)
from scripts.l1_collect.metadata_extractor import extract_official_number

_DATE_OK = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


@dataclass
class Decision:
    action: str                       # fix | queue | noop
    new_date: "str | None" = None
    date_method: "str | None" = None
    new_id: "str | None" = None
    reason: str = ""
    offnum_current: str = ""
    offnum_reextracted: str = ""
    offnum_flag: bool = False


def body_of(text: str) -> str:
    if text.startswith("---\n"):
        try:
            return text[text.index("\n---\n", 4) + 5:]
        except ValueError:
            pass
    return text


def _year_in_range(date_str: str, today_year: int) -> bool:
    if not _DATE_OK.match(date_str or ""):
        return False
    return 1990 <= int(date_str[:4]) <= today_year


def compute_new_id(old_id: str, new_year: int, existing_ids) -> str:
    parts = (old_id or "").split("_")
    if len(parts) < 4:
        return old_id
    base = f"P_{new_year}_{parts[2]}_{'_'.join(parts[3:])}"
    if base not in existing_ids:
        return base
    for suf in "abcdefghij":
        cand = f"{base}_{suf}"
        if cand not in existing_ids:
            return cand
    return base


def decide(fm: dict, body: str, today_year: int, existing_ids=frozenset()) -> Decision:
    cur_date = str(fm.get("date") or "")
    cur_id = str(fm.get("id") or "")

    cur_off = str(fm.get("official_number") or "")
    re_off = extract_official_number(body)
    offnum_flag = bool(cur_off) and (re_off != cur_off)

    authoritative = pick_luokuan_strict(body)                  # 高置信落款,否则入队不乱改
    broken = not _year_in_range(cur_date, today_year)          # 空/格式错/未来年/过古
    # 误标 = 实为正文生效/截止日,且未同时作为落款出现(发文日==生效日时不算误标)
    mislabel = (is_effective_or_deadline_date(body, cur_date)
                and not appears_as_issuance(body, cur_date))
    wrong = broken or mislabel

    d = Decision(action="noop", offnum_current=cur_off,
                 offnum_reextracted=re_off, offnum_flag=offnum_flag)
    if not wrong:
        d.reason = "date 合理且非误标 → 信任不动"
        return d
    if not (authoritative and _year_in_range(authoritative, today_year)
            and authoritative != cur_date):
        d.action = "queue"
        d.reason = ("破损/未来年" if broken else "生效/截止误标") + ";落款抽不到可信发文日"
        return d

    d.action = "fix"
    d.new_date = authoritative
    d.date_method = "body_chinese_date"
    d.reason = "破损/未来年→补落款" if broken else "生效/截止误标→改落款"
    year_changed = (not cur_date) or (authoritative[:4] != cur_date[:4])
    if year_changed:
        new_id = compute_new_id(cur_id, int(authoritative[:4]), set(existing_ids) - {cur_id})
        if new_id != cur_id:
            d.new_id = new_id
    return d


def apply_to_file(path: str, d: Decision, now_iso: str) -> list:
    """§C 就地写 date/id/aliases + provenance 审计。返回写了哪些字段。"""
    src = Path(path)
    m = _FM_RE.search(src.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{src} 无 frontmatter")
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2) or ""
    prov = fm.get("provenance") if isinstance(fm.get("provenance"), dict) else {}

    written = []
    old_date = str(fm.get("date") or "")
    if d.new_date and d.new_date != old_date:
        fm["date"] = d.new_date
        prov["date_fixed_at"] = now_iso
        prov["date_fixed_method"] = d.date_method or "body_chinese_date"
        prov["date_fixed_from"] = old_date
        written.append("date")
    if d.new_id:
        old_id = fm.get("id")
        aliases = fm.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = [aliases]
        if old_id and old_id not in aliases:
            aliases.append(old_id)
        if d.new_id not in aliases:
            aliases.append(d.new_id)
        fm["aliases"] = aliases
        fm["id"] = d.new_id
        prov["id_fixed_at"] = now_iso
        prov["id_fixed_method"] = "id_recompute_from_metadata"
        prov["id_fixed_from"] = old_id
        written.append("id")
    fm["provenance"] = prov
    new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False)
    src.write_text(f"---\n{new_fm}---\n\n{body.lstrip(chr(10))}\n", encoding="utf-8")
    return written


# ───────────────────────── 编排 ─────────────────────────
def _load(path: Path):
    m = _FM_RE.search(path.read_text(encoding="utf-8"))
    if not m:
        return None, None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return None, None
    return (fm if isinstance(fm, dict) else None), (m.group(2) or "")


def scan(policies_dir: Path, today_year: int):
    files = sorted(policies_dir.glob("*.md"))
    existing = set()
    parsed = []
    for p in files:
        fm, body = _load(p)
        if fm is None:
            continue
        existing.add(str(fm.get("id") or ""))
        parsed.append((p, fm, body))
    results = []
    for p, fm, body in parsed:
        d = decide(fm, body, today_year, existing)
        if d.new_id:
            existing.add(d.new_id)
        results.append((p, fm, body, d))
    return results


def _esc(s):
    return html.escape(str(s or ""))


def render_html(results, out_path: Path, vault: str, mode: str):
    fixes = [(p, fm, d) for p, fm, b, d in results if d.action == "fix"]
    fix_date_only = [x for x in fixes if not x[2].new_id]
    fix_id = [x for x in fixes if x[2].new_id]
    queue = [(p, fm, d) for p, fm, b, d in results if d.action == "queue"]
    offnum = [(p, fm, d) for p, fm, b, d in results if d.offnum_flag]
    noop = sum(1 for *_, d in results if d.action == "noop")

    def rows(items):
        out = []
        for p, fm, d in items:
            out.append(
                f"<tr><td>{_esc(fm.get('id'))}</td><td>{_esc(fm.get('title'))[:46]}</td>"
                f"<td>{_esc(fm.get('date'))}</td><td><b>{_esc(d.new_date)}</b></td>"
                f"<td>{_esc(d.new_id)}</td><td>{_esc(d.reason)}</td></tr>")
        return "\n".join(out)

    def off_rows(items):
        return "\n".join(
            f"<tr><td>{_esc(fm.get('id'))}</td><td>{_esc(fm.get('title'))[:46]}</td>"
            f"<td>{_esc(d.offnum_current)}</td><td>{_esc(d.offnum_reextracted) or '∅'}</td></tr>"
            for p, fm, d in items)

    doc = f"""<!doctype html><meta charset=utf-8>
<title>date 误标回填 dry-run</title>
<style>body{{font:14px/1.5 -apple-system,sans-serif;max-width:1080px;margin:24px auto;padding:0 16px;color:#222}}
h1{{font-size:20px}} h2{{font-size:16px;margin-top:28px;border-bottom:1px solid #eee;padding-bottom:4px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} td,th{{border:1px solid #ddd;padding:5px 8px;text-align:left;vertical-align:top}}
th{{background:#f6f6f6}} .k{{display:inline-block;min-width:230px}} b{{color:#0a6}} .muted{{color:#888}}</style>
<h1>存量 date 误标回填 · {mode}</h1>
<p class=muted>vault: {_esc(vault)} · 共扫 {len(results)} 篇 · 生成 {_esc(datetime.datetime.now().astimezone().isoformat(timespec='seconds'))}</p>
<p>
<span class=k>自动修(同年·只改 date):<b>{len(fix_date_only)}</b></span>
<span class=k>自动修(跨年·改 date+id):<b>{len(fix_id)}</b></span><br>
<span class=k>入队人工(错但抽不到落款):<b>{len(queue)}</b></span>
<span class=k>official_number 待复核:<b>{len(offnum)}</b></span><br>
<span class=k>不动(信任):{noop}</span>
</p>
<h2>自动修 · 同年只改 date({len(fix_date_only)})</h2>
<table><tr><th>id</th><th>title</th><th>旧 date</th><th>新 date</th><th>新 id</th><th>理由</th></tr>
{rows(fix_date_only)}</table>
<h2>自动修 · 跨年改 date+id({len(fix_id)})<span class=muted> — id 变需配套派生层重指(§C,另跑)</span></h2>
<table><tr><th>id</th><th>title</th><th>旧 date</th><th>新 date</th><th>新 id</th><th>理由</th></tr>
{rows(fix_id)}</table>
<h2>入队人工({len(queue)})</h2>
<table><tr><th>id</th><th>title</th><th>date</th><th>—</th><th>—</th><th>理由</th></tr>
{rows(queue)}</table>
<h2>official_number 待复核 · 只标记不写({len(offnum)})</h2>
<table><tr><th>id</th><th>title</th><th>现 official_number</th><th>复算</th></tr>
{off_rows(offnum)}</table>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, type=Path)
    ap.add_argument("--state", default="state/date_backfill")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--same-year-only", action="store_true",
                    help="只 apply 不改 id 的同年修复(跨年 id 改需配套派生重指,默认 defer)")
    ap.add_argument("--show-diff", action="store_true")
    args = ap.parse_args()

    today_year = datetime.date.today().year
    policies_dir = args.vault / "0_raw" / "policies"
    results = scan(policies_dir, today_year)
    state = Path(args.state)
    state.mkdir(parents=True, exist_ok=True)

    fixes = [(p, fm, b, d) for p, fm, b, d in results if d.action == "fix"]
    queue = [(p, fm, b, d) for p, fm, b, d in results if d.action == "queue"]
    offnum = [(p, fm, b, d) for p, fm, b, d in results if d.offnum_flag]
    fix_id = [x for x in fixes if x[3].new_id]
    mode = "APPLY" if args.apply else "DRY-RUN"

    print(f"扫描 {len(results)} 篇 · 模式 {mode}")
    print(f"  自动修: {len(fixes)}(其中跨年改 id: {len(fix_id)})")
    print(f"  入队人工: {len(queue)}")
    print(f"  official_number 待复核: {len(offnum)}")

    render_html(results, state / "report.html", str(args.vault), mode)
    with (state / "queue.jsonl").open("w", encoding="utf-8") as f:
        for p, fm, b, d in queue:
            f.write(json.dumps({"id": fm.get("id"), "title": fm.get("title"),
                                "date": fm.get("date"), "reason": d.reason,
                                "file": p.name}, ensure_ascii=False) + "\n")
    print(f"  报告: {state / 'report.html'}  队列: {state / 'queue.jsonl'}")

    if args.show_diff:
        print("\n--- diff 预览(前 5 篇自动修)---")
        now_iso = "PREVIEW"
        for p, fm, b, d in fixes[:5]:
            old = p.read_text(encoding="utf-8")
            tmp = old
            # 仅预览 frontmatter 变化:复用 apply 逻辑到内存副本
            fmc = dict(fm)
            print(f"\n# {fm.get('id')}  ({d.reason})")
            print(f"  date: {fm.get('date')} → {d.new_date}"
                  + (f"\n  id: {fm.get('id')} → {d.new_id}" if d.new_id else ""))

    if args.apply:
        to_apply = [x for x in fixes if not x[3].new_id] if args.same_year_only else fixes
        if args.same_year_only:
            print(f"\n--same-year-only:仅 apply {len(to_apply)} 篇同年(跳过 {len(fix_id)} 篇跨年)")
        now_iso = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        log = []
        for p, fm, b, d in to_apply:
            written = apply_to_file(str(p), d, now_iso)
            log.append({"id": fm.get("id"), "new_id": d.new_id,
                        "old_date": fm.get("date"), "new_date": d.new_date,
                        "written": written, "file": p.name, "at": now_iso})
        with (state / "apply_log.jsonl").open("w", encoding="utf-8") as f:
            for e in log:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        applied_id_changes = sum(1 for *_, d in to_apply if d.new_id)
        print(f"\n✓ 写回 {len(log)} 篇 raw。日志: {state / 'apply_log.jsonl'}")
        print("⚠ commit/push 经 produce_and_push(白名单 0_raw/policies/)。")
        if applied_id_changes:
            print(f"⚠ 本次含 {applied_id_changes} 篇 id 变 → 需另跑派生层重指(§C),不与本次同 commit。")
        if args.same_year_only and fix_id:
            print(f"ℹ 跳过 {len(fix_id)} 篇跨年 id 改(defer,待配套派生重指单独排)。")
    else:
        print("\ndry-run 完成。--show-diff 看变更,--apply 真写(仍需操作者 push)。")


if __name__ == "__main__":
    main()
