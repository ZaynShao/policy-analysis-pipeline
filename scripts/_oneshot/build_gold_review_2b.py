"""②-B Task13:把多模型标注 + 我(4.8)对争议篇的裁决,合成 proposed_gold,渲染评审网页给用户核验。
输入 state/node2b/golden/labels_raw.json;输出 proposed_gold.json + gold_review.html。一次性。"""
from __future__ import annotations
import json, html
from pathlib import Path

BASE = Path("/Users/shaoziyuan/dev/政策分析-pipeline/state/node2b/golden")
ZH = {
    "v2g": "V2G车网互动", "vpp_theme": "虚拟电厂", "energy_storage_theme": "新型储能",
    "gas_station_transition_theme": "加油站转型", "equipment_renewal_theme": "设备更新/以旧换新",
    "green_power_trading_theme": "绿电交易", "charging_infra": "充电基础设施", "power_market": "电力市场",
    "carbon_market_theme": "碳市场", "petroleum_retail_compliance": "加油零售合规",
    "residential_charging": "居住区充电", "distribution_grid_opening": "配电网开放",
    "aggregator_access": "聚合商准入",
}
def tz(tid): return ZH.get(tid, tid)

# 我(4.8)读全文后的裁决(覆盖 consensus)。note=给用户看的理由。
OVERRIDES = {
    "P_2019_GZ_64193177": {  # 贵州电网建设
        "themes": ["distribution_grid_opening", "charging_infra"],
        "primary": "distribution_grid_opening",
        "scores": {"D1": 3, "D2": 3, "D3": 2, "D4": 3, "D5": 4, "D6": 2}, "importance": 3,
        "note": "主旨是省级电网/配电网建设(含增量配电改革试点),充电基建只是城网下一个子条 → primary 改 配电网开放(覆盖2/3模型的 charging_infra)。",
    },
    "P_1990_NEA_1162": {  # 1990 调峰
        "themes": ["power_market"], "primary": "power_market",
        "scores": {"D1": 3, "D2": 1, "D3": 4, "D4": 1, "D5": 2, "D6": 1}, "importance": 2,
        "note": "调峰/峰谷电价/分时/省网互供结算=电力市场机制(那个判'零主题'的模型错了);但1990历史文件,直接影响极低→重要性2。",
    },
    "P_2024_JL_232": {  # 吉林用户侧储能
        "themes": ["energy_storage_theme", "vpp_theme", "aggregator_access", "power_market", "v2g"],
        "primary": "energy_storage_theme",
        "scores": {"D1": 5, "D2": 4, "D3": 2, "D4": 4, "D5": 4, "D6": 4}, "importance": 4,
        "note": "补标(原仅1模型出活)。用户侧储能=主旨;含组建VPP/聚合商参与市场+峰谷电价机制+规模化车网互动。滴滴电力高相关。",
    },
    "P_2025_GO_d433682b": {  # 宁德 电动宁德
        "themes": ["charging_infra", "residential_charging", "equipment_renewal_theme"],
        "primary": "charging_infra",
        "scores": {"D1": 4, "D2": 4, "D3": 1, "D4": 5, "D5": 4, "D6": 3}, "importance": 3,
        "note": "补标(原3模型全失败)。'电动宁德'实施意见,滴滴核心=充换电基建(居民区/老旧小区公共桩+农村)+以旧换新置换补贴。⚠raw误标'国家/未知机构',实为宁德市级→D3按市级=1(raw的region错,归②-A另修,本步不动raw)。",
    },
    "P_2022_GO_6a4cc949": {  # 新能源高质量发展
        "themes": ["green_power_trading_theme", "power_market", "energy_storage_theme", "distribution_grid_opening", "vpp_theme"],
        "primary": "green_power_trading_theme",
        "scores": {"D1": 4, "D2": 3, "D3": 5, "D4": 3, "D5": 3, "D6": 3}, "importance": 4,
        "note": "⚠高歧义(3模型 primary 各异 green/power_market/vpp)。这是一篇极宽的新能源高质量发展国办函,绿电交易/绿证/消纳(四+八)是最具体、复现的滴滴相关机制→取 green_power_trading 为 primary;但 power_market/储能 同样成立,留你定。",
    },
}

data = json.load(open(BASE / "labels_raw.json"))
res = data["results"]
samp = {s["pid"]: s for s in json.load(open(BASE / "sample_pids.json"))}

proposed = []
for r in res:
    pid = r["pid"]
    cons = r.get("consensus") or {}
    ov = OVERRIDES.get(pid)
    if ov:
        g = {"themes": ov["themes"], "primary_theme": ov["primary"],
             "scores": ov["scores"], "importance": ov["importance"]}
        source = "我裁决"
        note = ov["note"]
    else:
        g = {"themes": cons.get("themes", []), "primary_theme": cons.get("primary_theme", ""),
             "scores": cons.get("scores"), "importance": cons.get("importance")}
        source = "consensus"
        note = ""
    disp = r.get("disputed", {})
    raw = r.get("raw", [])
    prims = [x.get("primary") or "∅" for x in raw]
    primary_split = len(set(prims)) > 1
    spread = disp.get("max_score_spread", 0) or 0
    tcounts = [len(x.get("themes", [])) for x in raw]
    theme_spread = (max(tcounts) - min(tcounts)) if tcounts else 0
    focus = bool(ov) or primary_split or spread >= 3 or theme_spread >= 3
    proposed.append({
        "pid": pid, "title": r["title"], "level": r["level"], "agreement": r["agreement"],
        "n_labelers": r["n_labelers"], "path": samp.get(pid, {}).get("path", ""),
        "gold": g, "source": source, "note": note,
        "primary_split": primary_split, "score_spread": spread, "theme_spread": theme_spread,
        "focus": focus, "raw": raw,
    })

# 落 proposed_gold.json(供冻结步骤用)
json.dump(proposed, open(BASE / "proposed_gold.json", "w"), ensure_ascii=False, indent=2)

# ---------- 渲染 HTML ----------
def esc(s): return html.escape(str(s if s is not None else ""))
def themes_str(ts): return "、".join(tz(t) for t in ts) if ts else "（无/零主题）"

def raw_block(raw):
    rows = []
    for x in raw:
        sc = x.get("scores", {})
        scs = " ".join(f"{d}{sc.get(d,'?')}" for d in ("D1","D2","D3","D4","D5","D6"))
        rows.append(
            f"<tr><td class=m>{esc(x.get('model'))}</td>"
            f"<td>{esc('、'.join(tz(t) for t in x.get('themes',[])) or '∅')}</td>"
            f"<td class=pri>{esc(tz(x.get('primary')) if x.get('primary') else '∅')}</td>"
            f"<td class=sc>{esc(scs)}</td>"
            f"<td class=rat>{esc((x.get('rationale') or '')[:120])}</td></tr>")
    return ("<table class=raw><tr><th>模型</th><th>themes</th><th>primary</th>"
            "<th>D1-D6</th><th>理由</th></tr>" + "".join(rows) + "</table>")

def card(p):
    g = p["gold"]; sc = g["scores"] or {}
    scs = " ".join(f"{d}={sc.get(d,'?')}" for d in ("D1","D2","D3","D4","D5","D6"))
    flags = []
    if p["source"] == "我裁决": flags.append("<span class='fl adj'>我裁决</span>")
    if p["primary_split"]: flags.append("<span class='fl ps'>primary分歧</span>")
    if p["score_spread"] >= 3: flags.append(f"<span class='fl ss'>分跨度{p['score_spread']}</span>")
    if p["theme_spread"] >= 3: flags.append(f"<span class='fl ts'>主题数差{p['theme_spread']}</span>")
    note = f"<div class=note>💡 {esc(p['note'])}</div>" if p["note"] else ""
    return f"""<div class="card {'focus' if p['focus'] else ''}">
  <div class=hd><span class=lv>{esc(p['level'])}</span>
    <span class=tt>{esc(p['title'][:46])}</span>
    <span class=ag ag-{esc(p['agreement'])}>{esc(p['agreement'])}·{esc(p['n_labelers'])}模型</span>
    {''.join(flags)}</div>
  <div class=gold><b>建议 gold</b> &nbsp; 主题: {esc(themes_str(g['themes']))}
    &nbsp;|&nbsp; <b>primary</b>: {esc(tz(g['primary_theme']) if g['primary_theme'] else '∅')}
    &nbsp;|&nbsp; 重要性 <b>{esc(g['importance'])}</b> &nbsp;({esc(scs)})</div>
  {note}
  {raw_block(p['raw'])}
</div>"""

focus = [p for p in proposed if p["focus"]]
rest = [p for p in proposed if not p["focus"]]
n_adj = sum(1 for p in proposed if p["source"] == "我裁决")
n_ps = sum(1 for p in proposed if p["primary_split"])

doc = f"""<!DOCTYPE html><html lang=zh-CN><head><meta charset=UTF-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>②-B golden 评审 · 你核验我标得对不对</title>
<style>
 body{{margin:0;background:#f5f7fa;color:#1c2530;font:14px/1.6 -apple-system,"PingFang SC",sans-serif}}
 .wrap{{max-width:1080px;margin:0 auto;padding:28px 20px 80px}}
 h1{{font-size:23px;margin:0 0 4px}} .sub{{color:#5b6b7b;margin:0 0 20px}}
 .legend{{background:#fff;border:1px solid #e3e8ee;border-radius:10px;padding:12px 16px;margin-bottom:22px;font-size:13px}}
 h2{{font-size:17px;margin:26px 0 12px;border-left:4px solid #2b6cb0;padding-left:10px}}
 .card{{background:#fff;border:1px solid #e3e8ee;border-radius:10px;padding:14px 16px;margin:0 0 14px}}
 .card.focus{{border-left:4px solid #d9822b;background:#fffdf8}}
 .hd{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px}}
 .lv{{background:#eef2f7;border-radius:4px;padding:1px 7px;font-size:12px;color:#5b6b7b}}
 .tt{{font-weight:600;flex:1;min-width:240px}}
 .ag{{font-size:12px;border-radius:10px;padding:1px 8px;color:#fff}}
 .ag-high{{background:#1a8f4c}} .ag-mid{{background:#b8860b}} .ag-low{{background:#c0392b}} .ag-failed{{background:#777}}
 .fl{{font-size:11px;border-radius:4px;padding:1px 6px;color:#fff}}
 .fl.adj{{background:#8e44ad}} .fl.ps{{background:#c0392b}} .fl.ss{{background:#d9822b}} .fl.ts{{background:#6b7c93}}
 .gold{{background:#f0f6ff;border-radius:6px;padding:8px 10px;margin:6px 0}}
 .note{{color:#8a5a00;font-size:13px;margin:6px 0;background:#fff7e8;border-radius:6px;padding:7px 10px}}
 table.raw{{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px}}
 table.raw th{{background:#f0f4f8;color:#5b6b7b;text-align:left;padding:4px 7px;font-weight:600}}
 table.raw td{{border-top:1px solid #eef1f4;padding:4px 7px;vertical-align:top}}
 td.m{{font-weight:600;white-space:nowrap}} td.pri{{white-space:nowrap;color:#2b6cb0}}
 td.sc{{white-space:nowrap;font-family:ui-monospace,monospace;color:#555}} td.rat{{color:#777}}
</style></head><body><div class=wrap>
<h1>②-B golden 评审表</h1>
<p class=sub>50 篇 × 3 模型(opus/sonnet/haiku)独立标 + 我(4.8)对争议篇裁决。<b>你的活=核验我标得对不对(尤其橙色"重点核验"区)</b>,不是从头标。</p>
<div class=legend>
 一致性:<span class=ag ag-high>high {data['by_level']['high']}</span>
 <span class=ag ag-mid>mid {data['by_level']['mid']}</span>
 <span class=ag ag-low>low {data['by_level']['low']}</span>
 <span class=ag ag-failed>failed {data['by_level']['failed']}</span>
 &nbsp;|&nbsp; 我裁决 {n_adj} 篇 · primary分歧 {n_ps} 篇 &nbsp;|&nbsp;
 标记:<span class=fl adj>我裁决</span><span class=fl ps>primary分歧</span><span class=fl ss>分数跨度大</span><span class=fl ts>主题数差大</span>
 <br>看法:每篇上排=我建议的 gold,下表=三个模型各自原始标注(看它们怎么分的)。觉得我哪篇错了→告诉我 pid + 你的意见。
</div>
<h2>重点核验 · {len(focus)} 篇(我做了判断 / 模型分歧大)</h2>
{''.join(card(p) for p in focus)}
<h2>高/中一致 · {len(rest)} 篇(consensus 直接采纳,抽查即可)</h2>
{''.join(card(p) for p in rest)}
</div></body></html>"""

out = BASE / "gold_review.html"
out.write_text(doc, encoding="utf-8")
print("focus(重点核验):", len(focus), "| rest:", len(rest), "| 我裁决:", n_adj)
print("HTML ->", out)
print("proposed_gold.json ->", BASE / "proposed_gold.json")
