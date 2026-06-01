"""②-B Task13 一次性:从 935 篇分层抽 ~50 篇做 golden 样本。
确定性(无随机):quota-greedy 覆盖 theme × region层级 × 单/多/零主题。
theme 命中=registry alias 子串匹配(召回代理,仅用于抽样分层,非真值)。
输出 state/node2b/golden/sample_pids.json + 打印分布。
用法: python3 scripts/_oneshot/sample_golden_2b.py [--target 50]
"""
from __future__ import annotations
import sys, json, argparse
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import yaml
from scripts.l1_audit.corpus import load_policies

DEFAULT_VAULT = str(Path.home() / "Documents" / "Zayn Main" / "政策分析")


def level_bucket(level: str) -> str:
    if level == "国家": return "国家"
    if level == "省": return "省"
    if level in ("市", "区", "县"): return "地方"
    return "其他"


def ntheme_bucket(n: int) -> str:
    if n == 0: return "零主题"
    if n == 1: return "单主题"
    if n == 2: return "双主题"
    return "多主题"


def match_themes(text: str, themes: list) -> list:
    hit = []
    for t in themes:
        for a in (t.get("aliases") or []):
            if a and a in text:
                hit.append(t["id"]); break
    return hit


def build(vault: str, target: int, min_per_theme: int = 3):
    themes = (yaml.safe_load(Path(f"{vault}/_meta/themes_registry.yaml").read_text(encoding="utf-8")) or {}).get("themes", [])
    theme_ids = [t["id"] for t in themes]
    recs = load_policies(f"{vault}/0_raw/policies")

    meta = {}
    for r in recs:
        text = (r.title or "") + "\n" + (r.body_head or "")
        mt = match_themes(text, themes)
        lvl = (r.raw_fm.get("region") or {}).get("level", "")
        meta[r.pid] = {"pid": r.pid, "title": r.title, "path": r.path,
                       "level": lvl, "level_bucket": level_bucket(lvl),
                       "matched_themes": mt, "n_themes": len(mt)}

    # 配额(want):theme 每个 min_per_theme;层级偏置(省过多→压低);单/多/零都要
    quota = {f"theme:{tid}": min_per_theme for tid in theme_ids}
    quota.update({"lvl:国家": 12, "lvl:省": 15, "lvl:地方": 12, "lvl:其他": 1,
                  "nt:零主题": 5, "nt:单主题": 10, "nt:双主题": 8, "nt:多主题": 8})

    def cells(m):
        c = [f"lvl:{m['level_bucket']}", f"nt:{ntheme_bucket(m['n_themes'])}"]
        c += [f"theme:{tid}" for tid in m["matched_themes"]]
        return c

    selected, remaining = {}, dict(quota)
    pool = sorted(meta.values(), key=lambda m: m["pid"])  # 稳定序

    def score(m):
        return sum(1 for c in cells(m) if remaining.get(c, 0) > 0)

    while len(selected) < target:
        best = None; best_s = 0
        for m in pool:
            if m["pid"] in selected:
                continue
            s = score(m)
            if s > best_s:
                best_s, best = s, m
        if best is None or best_s == 0:
            break  # 所有配额已满足
        selected[best["pid"]] = best
        for c in cells(best):
            if c in remaining:
                remaining[c] = max(0, remaining[c] - 1)

    # 配额满足后若不足 target,按"补欠表达"继续填(确定性):优先命中当前出现最少 cell 的政策
    while len(selected) < target:
        seen = Counter(c for m in selected.values() for c in cells(m))
        best = None; best_s = -1.0
        for m in pool:
            if m["pid"] in selected:
                continue
            s = sum(1.0 / (1 + seen[c]) for c in cells(m))
            if s > best_s:
                best_s, best = s, m
        if best is None:
            break
        selected[best["pid"]] = best

    return theme_ids, list(selected.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--target", type=int, default=50)
    ap.add_argument("--out", default="state/node2b/golden/sample_pids.json")
    a = ap.parse_args()

    theme_ids, picks = build(a.vault, a.target)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"抽样 {len(picks)} 篇 -> {a.out}\n")
    print("层级分布:", dict(Counter(m["level"] or "(空)" for m in picks)))
    print("单/多/零:", dict(Counter(ntheme_bucket(m["n_themes"]) for m in picks)))
    tc = Counter(t for m in picks for t in m["matched_themes"])
    print("\n各 theme 命中篇数(抽样内):")
    for tid in theme_ids:
        print(f"  {tid:32s} {tc.get(tid,0)}")
    miss = [t for t in theme_ids if tc.get(t, 0) == 0]
    if miss:
        print("\n⚠ 抽样内未覆盖的 theme:", miss)


if __name__ == "__main__":
    main()
