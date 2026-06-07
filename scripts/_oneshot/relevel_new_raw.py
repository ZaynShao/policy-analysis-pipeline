"""Task12 收口:重导本会话 backfill 新写 raw 的 region.level(确定性·§C)。

背景:region 修复(commit 45eba2c)之前跑的省级 backfill,95篇省级政策被旧 ingester
误标 level=市(name=云南省/level=市 内部矛盾)。45eba2c 之后的 city/nea 已正确。
此脚本只动 vault 未提交(untracked)的新文件,按 region.name/code 确定性重算 level:
  - name 以 省/自治区 结尾 且 level≠省 → 省
  - code=000000 且 level≠国家 → 国家(name=全国)
  - 其余(市/直辖市/已正确)不动
不碰旧 ②-A 文件(只取 git untracked)。body 逐字保留,只重写 frontmatter + 加 provenance.relevel。
DRY_RUN=1 只打印不写。
"""
from __future__ import annotations
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yaml

VAULT = Path.home() / "Documents/Zayn Main/政策分析"
CST = timezone(timedelta(hours=8))
DRY = os.environ.get("DRY_RUN") == "1"


def untracked_md() -> list:
    out = subprocess.run(
        ["git", "-C", str(VAULT), "status", "--porcelain", "-z", "0_raw/policies/"],
        capture_output=True, text=True).stdout
    files = []
    for ent in out.split("\0"):
        if not ent:
            continue
        status, _, path = ent.partition(" ") if ent[:2].strip() else (ent[:2], "", ent[3:])
        # porcelain -z: "XY path";取 ?? 的 path
        if ent.startswith("??"):
            files.append(ent[3:])
    return files


def new_level(name: str, code: str, lvl: str):
    if (name.endswith("省") or name.endswith("自治区")) and lvl != "省":
        return "省", name
    if code == "000000" and lvl != "国家":
        return "国家", "全国"
    return None, None


def main() -> None:
    files = untracked_md()
    print(f"未提交新文件 {len(files)}  DRY={DRY}")
    fixed = 0
    now = datetime.now(CST).isoformat(timespec="seconds")
    for fn in files:
        p = VAULT / fn
        if not p.exists():
            print("  缺", fn[:50])
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", txt, re.S)
        if not m:
            continue
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            continue
        reg = fm.get("region") or {}
        name, code, lvl = str(reg.get("name") or ""), str(reg.get("code") or ""), str(reg.get("level") or "")
        nl, nn = new_level(name, code, lvl)
        if nl is None:
            continue
        fixed += 1
        if fixed <= 6:
            print(f"  {lvl}→{nl}  {name}  {p.name[:34]}")
        if DRY:
            continue
        reg["level"], reg["name"] = nl, nn
        fm["region"] = reg
        prov = fm.get("provenance") or {}
        prov["relevel_at"] = now
        prov["relevel_method"] = "region.code/name deterministic"
        prov["relevel_from"] = lvl
        fm["provenance"] = prov
        new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False)
        p.write_text(f"---\n{new_fm}---\n{m.group(2)}", encoding="utf-8")
    print(f"{'(dry)需改' if DRY else '已改'} {fixed}")


if __name__ == "__main__":
    main()
