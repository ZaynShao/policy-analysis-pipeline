"""Task12 收口:L1 raw 层省×主题覆盖审计(区别于 Task8 audit_coverage 读 L2 business_view)。

本线是 L1,backfill 改变的是 raw,而 raw 无 theme 标注(theme 是 ②-B 产物)。故用关键词
直接在 raw(title+正文头)上量省×{充电/加油/电力}覆盖,并标本会话新增量。region 按
region.code 前2位映射到省(市级政策正确归省)。emit HTML → state/l1_gate/audit_post.html。

注意:这是 L1 采集覆盖的真值;Task8 audit_coverage.py(bv-based)需 ②-B 跑过新 raw +
theme 词表对齐(13theme vs 旧3key)才有意义 = 留 backlog。
"""
from __future__ import annotations
import argparse
import re
import subprocess
from pathlib import Path
import yaml

from scripts.l1_collect.channel_discovery import _PROV_CODE

VAULT = Path.home() / "Documents/Zayn Main/政策分析"
POL = VAULT / "0_raw/policies"
PREFIX = {code: name for name, code in _PROV_CODE.items()}  # "32"->"江苏省"
KEY = {"广东省", "江苏省", "浙江省", "山东省", "四川省", "河南省", "湖北省",
       "湖南省", "安徽省", "河北省", "福建省", "上海市", "北京市", "重庆市"}
THEMES = {
    "充电": ["充电", "充电桩", "换电", "充换电", "电动汽车", "车网互动", "V2G", "充电设施"],
    "加油": ["成品油", "加油站", "油气", "天然气", "加氢", "油品", "燃油", "管网"],
    "电力": ["电力", "电网", "储能", "绿电", "光伏", "风电", "现货市场", "需求响应",
              "配电", "电价", "新能源", "电源"],
    "平台监管": ["平台经济", "反垄断", "反不正当竞争", "市场监管",
                "网络交易", "互联网平台", "经营者集中"],
}


def new_files() -> set:
    out = subprocess.run(["git", "-C", str(VAULT), "status", "--porcelain", "-z",
                          "0_raw/policies/"], capture_output=True, text=True).stdout
    return {e[3:].split("/")[-1] for e in out.split("\0") if e.startswith("??")}


def build():
    new = new_files()
    # prov -> {theme: [total, new]} + prov->total_raw
    agg = {p: {t: [0, 0] for t in THEMES} for p in PREFIX.values()}
    totals = {p: 0 for p in PREFIX.values()}
    for f in POL.glob("*.md"):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", txt, re.S)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            continue
        reg = fm.get("region") or {}
        prov = PREFIX.get(str(reg.get("code") or "")[:2])
        if not prov:
            continue
        totals[prov] += 1
        blob = str(fm.get("title") or "") + " " + m.group(2)[:600]
        isnew = f.name in new
        for t, kws in THEMES.items():
            if any(k in blob for k in kws):
                agg[prov][t][0] += 1
                if isnew:
                    agg[prov][t][1] += 1
    return agg, totals


def render(agg, totals) -> str:
    rows = ""
    for p in sorted(PREFIX.values(), key=lambda x: -totals[x]):
        if totals[p] == 0:
            continue
        bold = "font-weight:bold" if p in KEY else ""
        cells = ""
        for t in THEMES:
            tot, n = agg[p][t]
            zero = ' class="zero"' if (tot == 0 and p in KEY) else ""
            badge = f' <span style="color:#080">+{n}</span>' if n else ""
            cells += f'<td{zero}>{tot}{badge}</td>'
        rows += f'<tr><td style="{bold}">{p}</td><td>{totals[p]}</td>{cells}</tr>'
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>L1 raw覆盖审计</title>
<style>body{{font-family:system-ui;margin:2em}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:4px 10px;text-align:right}}td:first-child{{text-align:left}}
th{{background:#eee}}.zero{{background:#fcc}}</style></head><body>
<h1>L1 采集覆盖审计(raw 层)</h1>
<p>省×主题 = raw 政策中命中该主题关键词的篇数;<b style="color:#080">+N</b>=本会话 backfill 新增;
红底=重点省该主题为 0(采集/归属缺口)。数据源 0_raw/policies/(市级按 region.code 归省)。</p>
<table><tr><th>省</th><th>总raw</th>{''.join(f'<th>{t}</th>' for t in THEMES)}</tr>
{rows}</table>
<h2>关键发现</h2><ul>
<li>backfill 体量集中在<b>电力/能源</b>(发改委驱动),非充电。</li>
<li><b>江浙充电缺口未闭</b>:浙江充电 raw=0、江苏充电全为存量(0 新增)→ 留重点城市充电 promote + 商务/市监专项 + B7 缺口归因环。</li>
<li>Task8 audit_coverage.py(读 business_view)需 ②-B 跑过新 raw + theme 词表对齐才有意义(backlog)。</li>
</ul></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="state/l1_gate/audit_post.html")
    a = ap.parse_args()
    agg, totals = build()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(agg, totals), encoding="utf-8")
    # 控制台摘要
    print(f"[raw-audit] → {out}")
    for p in ("江苏省", "浙江省", "四川省"):
        c = agg[p]["充电"]
        print(f"  {p} 充电 raw={c[0]} (新增 {c[1]}) · 总 raw {totals[p]}")


if __name__ == "__main__":
    main()
