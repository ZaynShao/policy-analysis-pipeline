"""②-B Task13:golden_clean + 拟真埋错 → golden_v1.jsonl(judge 校准用)。
clean 记录 is_planted=false(judge 应 accept);planted 记录 is_planted=true(judge 应 reject)。
埋错由 4.8 手工设计,仿"便宜模型真会犯的"语义错。一次性。
渲染 planted_review.html 给用户核"是否真坑+像不像便宜模型会犯"。"""
import json, html
from pathlib import Path

BASE = Path("/Users/shaoziyuan/dev/政策分析-pipeline/state/node2b/golden")
clean = {c["pid"]: c for c in json.load(open(BASE / "golden_clean.json"))}

def imp(s):  # round(.4D1+.4D2+.2D3)
    return round(0.4 * s["D1"] + 0.4 * s["D2"] + 0.2 * s["D3"])

# 每条:pid + error_type + note + 对 gold 的变异(只列要改的)
PLANTED = [
    {"pid": "P_2013_BJ_cee25b16", "error_type": "over_attach",
     "note": "纯碳交易试点,被乱加 电力市场+绿电交易(碳→市场/绿电的表面联想)",
     "mut": {"themes": ["carbon_market_theme", "power_market", "green_power_trading_theme"]}},
    {"pid": "P_2024_JL_232", "error_type": "miss_theme",
     "note": "用户侧储能政策,只挂了储能,漏掉它明确写的 VPP/聚合商/车网互动",
     "mut": {"themes": ["energy_storage_theme"], "primary_theme": "energy_storage_theme"}},
    {"pid": "P_2022_CQ_229620a1", "error_type": "wrong_primary_comprehensive",
     "note": "横跨7主题的综合议案,被当成单焦点政策:comprehensive 抹成 false 且硬指 primary=充电",
     "mut": {"comprehensive": False, "primary_theme": "charging_infra"}},
    {"pid": "P_2017_GD_70875d73", "error_type": "underrate_local",
     "note": "广州充电强化政策(滴滴高相关),因'只是市级'被压分:D1/D2→2,重要性掉到2",
     "mut": {"scores_set": {"D1": 2, "D2": 2}}},
    {"pid": "P_2025_BJ_3701c968", "error_type": "overrate_irrelevant",
     "note": "这是'年度总目录索引'(噪声),被幻觉成充电政策且给到重要性4",
     "mut": {"themes": ["charging_infra"], "primary_theme": "charging_infra",
             "scores_set": {"D1": 4, "D2": 4, "D3": 2}}},
    {"pid": "P_2012_SH_020", "error_type": "hallucinated_impact",
     "note": "居民阶梯电价(非滴滴业务),被编造充电/储能业务影响",
     "mut": {"themes": ["power_market"], "primary_theme": "power_market",
             "scores_set": {"D1": 3, "D2": 3, "D3": 2},
             "影响分析": {"加油": "无直接影响",
                      "充电": "居民阶梯电价下调利好充电成本,扩大充电业务空间",
                      "电力_储能_V2G_交易": "为居民侧储能套利创造条件"}}},
    {"pid": "P_2024_NDRC_718", "error_type": "miss_theme",
     "note": "车网互动试点(覆盖充电/VPP/聚合/绿电多面),被锚在标题只留 v2g",
     "mut": {"themes": ["v2g"], "primary_theme": "v2g"}},
    {"pid": "P_2020_NDRC_06306aac", "error_type": "underrate_national",
     "note": "电力中长期交易基本规则(国家级地基性规则),被严重低估:D1=2/D2=1,重要性掉到2",
     "mut": {"scores_set": {"D1": 2, "D2": 1}}},
    {"pid": "P_2015_TJ_9ec9c169", "error_type": "over_attach_zero",
     "note": "光伏发电项目建设管理(弱相关零主题),被挂上 绿电交易+电力市场 且抬到重要性3",
     "mut": {"themes": ["green_power_trading_theme", "power_market"],
             "primary_theme": "green_power_trading_theme",
             "scores_set": {"D1": 3, "D2": 3, "D3": 2}}},
]

def clean_record(c):
    g = c["gold"]
    return {"record_id": c["pid"], "pid": c["pid"], "is_planted": False, "error_type": None,
            "title": c["title"], "level": c["level"],
            "themes": g["themes"], "primary_theme": g["primary_theme"],
            "comprehensive": g["comprehensive"], "scores": g["scores"],
            "importance": g["importance"], "影响分析": None}

def planted_record(p):
    c = clean[p["pid"]]; g = c["gold"]; m = p["mut"]
    scores = dict(g["scores"])
    if "scores_set" in m: scores.update(m["scores_set"])
    themes = m.get("themes", g["themes"])
    primary = m.get("primary_theme", g["primary_theme"])
    comp = m.get("comprehensive", g["comprehensive"])
    return {"record_id": p["pid"] + "__planted", "pid": p["pid"], "is_planted": True,
            "error_type": p["error_type"], "planted_note": p["note"],
            "title": c["title"], "level": c["level"],
            "themes": themes, "primary_theme": primary, "comprehensive": comp,
            "scores": scores, "importance": imp(scores), "影响分析": m.get("影响分析")}

records = [clean_record(c) for c in clean.values()] + [planted_record(p) for p in PLANTED]
with open(BASE / "golden_v1.jsonl", "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

n_clean = sum(1 for r in records if not r["is_planted"])
n_plant = sum(1 for r in records if r["is_planted"])
print(f"golden_v1.jsonl: {len(records)} 条(clean {n_clean} + planted {n_plant})")

# ---- planted 核验 HTML ----
def esc(s): return html.escape(str(s if s is not None else ""))
def sc(s): return " ".join(f"{k}{s.get(k,'?')}" for k in ("D1","D2","D3","D4","D5","D6"))
rows = []
for p in PLANTED:
    c = clean[p["pid"]]; g = c["gold"]; pr = planted_record(p)
    rows.append(f"""<tr>
      <td>{esc(c['level'])}<br><b>{esc(p['error_type'])}</b></td>
      <td>{esc(c['title'][:30])}</td>
      <td class=ok>主题 {esc('、'.join(g['themes']) or '∅')}<br>primary {esc(g['primary_theme'] or '∅')}{' ·综合' if g['comprehensive'] else ''}<br>重要性 {esc(g['importance'])} [{esc(sc(g['scores']))}]</td>
      <td class=bad>主题 {esc('、'.join(pr['themes']) or '∅')}<br>primary {esc(pr['primary_theme'] or '∅')}{' ·综合' if pr['comprehensive'] else ''}<br>重要性 {esc(pr['importance'])} [{esc(sc(pr['scores']))}]{('<br>影响:'+esc(list((pr['影响分析'] or {}).values()))) if pr['影响分析'] else ''}</td>
      <td>{esc(p['note'])}</td></tr>""")
doc = f"""<!DOCTYPE html><html lang=zh-CN><head><meta charset=UTF-8>
<title>埋错核验 · 是否真坑 + 像不像便宜模型会犯</title>
<style>body{{font:14px/1.6 -apple-system,"PingFang SC",sans-serif;margin:0;background:#f5f7fa;color:#1c2530}}
.wrap{{max-width:1100px;margin:0 auto;padding:28px 20px 70px}}h1{{font-size:22px}}
.sub{{color:#5b6b7b;margin-bottom:18px}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e3e8ee;border-radius:8px;overflow:hidden}}
th,td{{padding:9px 11px;border-bottom:1px solid #eef1f4;vertical-align:top;font-size:13px;text-align:left}}
th{{background:#f0f4f8;color:#5b6b7b}}
td.ok{{background:#eef9f1}} td.bad{{background:#fdeeee}}
b{{color:#8e44ad}}</style></head><body><div class=wrap>
<h1>埋错副本核验 · {n_plant} 条</h1>
<p class=sub>左绿=正确 gold,右红=故意埋的错(judge 应当抓出=reject)。<b>你核两件</b>:① 这是不是真坑(右边确实错);② 像不像便宜模型真会犯的(保证 judge 考得公平)。觉得哪条不像/太假→告诉我换。</p>
<table><tr><th>层级/错型</th><th>政策</th><th>✅ 正确 gold</th><th>❌ 埋错(应被 reject)</th><th>为什么这么埋(拟真理由)</th></tr>
{''.join(rows)}</table></div></body></html>"""
(BASE / "planted_review.html").write_text(doc, encoding="utf-8")
print("planted_review.html ->", BASE / "planted_review.html")
from collections import Counter
print("错型分布:", dict(Counter(p["error_type"] for p in PLANTED)))
