"""Task12 收口侦察:在 vault 未提交(untracked)新 raw 里识别『官方政策解读/问答/图解』。

只读不写。识别依据 = title 含: 政策解读/【文字解读/解读材料/问答/答记者问/一图读懂/图解。
输出每篇:文件名 / title / issuer / region / date / source_url(用于 related_policy best-effort)。
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path
import yaml

VAULT = Path.home() / "Documents/Zayn Main/政策分析"
MARKERS = ["政策解读", "【文字解读", "文字解读", "解读材料", "问答", "答记者问", "一图读懂", "图解", "图读"]


def untracked_policies() -> list:
    out = subprocess.run(
        ["git", "-C", str(VAULT), "status", "--porcelain", "-z", "0_raw/policies/"],
        capture_output=True, text=True).stdout
    return [ent[3:] for ent in out.split("\0") if ent.startswith("??")]


def main() -> None:
    files = untracked_policies()
    hits = []
    for fn in files:
        p = VAULT / fn
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
        if not m:
            continue
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            continue
        title = str(fm.get("title") or "")
        if any(k in title for k in MARKERS):
            hits.append((fn, fm))
    print(f"untracked={len(files)}  解读命中={len(hits)}\n")
    for fn, fm in hits:
        reg = fm.get("region") or {}
        print(f"--- {Path(fn).name}")
        print(f"    title : {fm.get('title')}")
        print(f"    issuer: {fm.get('issuer')}  region: {reg.get('level')}/{reg.get('name')}")
        print(f"    date  : {fm.get('date')}  themes: {fm.get('themes') or fm.get('business_tag')}")
        print(f"    url   : {fm.get('source_url')}")


if __name__ == "__main__":
    main()
