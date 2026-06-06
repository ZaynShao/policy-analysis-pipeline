"""③-C Task8 后处理:把 labels_raw.json + golden_pairs.jsonl(骨架) 合并,
渲一张评审页给用户裁 low + 抽查 high。一次性脚本。

输入:
  state/node3c/golden/labels_raw.json     —— Task8 外包跑回的多模型标注
  state/node3c/golden/golden_pairs.jsonl  —— Task7 抽样冻结的骨架(35 真 + 10 埋错)
输出:
  state/node3c/golden/3c_gold_review.html —— 评审页
"""
from __future__ import annotations
import json, html, hashlib
from pathlib import Path
from collections import OrderedDict

BASE = Path("/Users/shaoziyuan/dev/政策分析-pipeline/state/node3c/golden")
LABELS = BASE / "labels_raw.json"
GOLDEN = BASE / "golden_pairs.jsonl"
OUT_HTML = BASE / "3c_gold_review.html"

REL_ZH = {
    "derives_from": "derives_from(下位承接上位)",
    "extends":      "extends(由试点扩到全国)",
    "iterates":     "iterates(同框架年度迭代/版本升级)",
    "aligns_with":  "aligns_with(同主题跨地区/部门对齐·无因果)",
}
DECISION_ZH = {"accept": "接受(关系成立)", "reject": "驳回(关系不成立)", "manual_review": "送人工"}

# 抽查 high 用的代表对(挑各 rel 各 stratum,5-8 条覆盖)
SPOT_CHECK_KEYS_HINT = [
    # (rel, picker) — picker 用于在该 rel 内挑第几条;后续构建时再确认
]

def esc(s):
    return html.escape(str(s) if s is not None else "")

def load_labels():
    return json.loads(LABELS.read_text(encoding="utf-8"))

def load_skeleton():
    out = OrderedDict()
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        key = (r["from"], r["to"], r["rel"])
        out[key] = r
    return out

def pick_spot_checks(label_results, skel):
    """从 high 里挑代表对给用户抽查。
    策略:每个 rel 挑 1-2 条(优先 stratum 多样、confidence 中等者),共 6 条。
    """
    # 按 rel 分组 high
    by_rel = {}
    for r in label_results:
        if r["agreement"] != "high":
            continue
        by_rel.setdefault(r["rel"], []).append(r)
    # 排序:取每个 rel 第 1 条和第 (len//2) 条
    picks = []
    for rel in ["derives_from", "extends", "iterates", "aligns_with"]:
        bucket = by_rel.get(rel, [])
        if not bucket:
            continue
        picks.append(bucket[0])
        if len(bucket) >= 4:
            picks.append(bucket[len(bucket) // 2])
    return picks

def render_card(idx, lbl, skel_row, kind):
    """kind ∈ {'low','spot'};决定卡片样式与提示语。"""
    key = (lbl["from"], lbl["to"], lbl["rel"])
    skel = skel_row or {}
    from_title = skel.get("from_title", "")
    to_title = skel.get("to_title", "")
    from_win = skel.get("from_window", "")
    to_win = skel.get("to_window", "")
    basis = skel.get("candidate_basis", [])
    stratum = skel.get("stratum", lbl.get("stratum", ""))

    rows = []
    for rr in lbl["raw"]:
        dec_cls = "ok" if rr["decision"] == "accept" else ("bad" if rr["decision"] == "reject" else "mid")
        rows.append(f"""<tr class="{dec_cls}">
<td class="m">{esc(rr['model'])}</td>
<td class="d">{esc(DECISION_ZH.get(rr['decision'], rr['decision']))}</td>
<td class="c">{esc(rr.get('confidence', ''))}</td>
<td class="r">{esc(rr.get('reason', ''))}</td>
</tr>""")

    consensus = lbl.get("consensus", {})
    consensus_str = (
        f"共识={esc(DECISION_ZH.get(consensus.get('decision',''), consensus.get('decision','')))}"
        f"  票数={esc(consensus.get('vote',{}))}  n_labelers={lbl.get('n_labelers','')}"
    )

    if kind == "low":
        header_badge = '<span class="bdg low">LOW · 需你裁</span>'
        prompt = '<div class="prompt">⮕ 请裁:<b>accept</b> / <b>reject</b> / <b>manual_review</b>(连理由)</div>'
    else:
        header_badge = '<span class="bdg spot">HIGH · 抽查</span>'
        prompt = '<div class="prompt">⮕ 只需说<b>过</b>或<b>有疑</b>。若有疑,贴你的判断+理由。</div>'

    bs = " · ".join(esc(b) for b in basis) if basis else ""

    return f"""
<section class="card">
<div class="cardhdr">
  <span class="idx">#{idx}</span> {header_badge}
  <span class="rel">{esc(REL_ZH.get(lbl['rel'], lbl['rel']))}</span>
  <span class="strt">stratum={esc(stratum)}</span>
</div>
<div class="pids">
  <div class="pid"><span class="lbl">from</span> <code>{esc(lbl['from'])}</code><div class="t">{esc(from_title)}</div></div>
  <div class="arrow">→</div>
  <div class="pid"><span class="lbl">to</span> <code>{esc(lbl['to'])}</code><div class="t">{esc(to_title)}</div></div>
</div>
<div class="meta">candidate_basis: {bs}</div>
<div class="wins">
  <div class="win"><div class="wlbl">from_window(judge 看到的承接句)</div><div class="wbody">{esc(from_win)}</div></div>
  <div class="win"><div class="wlbl">to_window</div><div class="wbody">{esc(to_win)}</div></div>
</div>
<div class="cons">{consensus_str}</div>
<table class="votes">
<thead><tr><th>模型</th><th>判定</th><th>conf</th><th>理由</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
{prompt}
</section>
"""

def render(label_data, skel):
    results = label_data["results"]
    lows = [r for r in results if r["agreement"] == "low"]
    spots = pick_spot_checks(results, skel)

    cards = []
    for i, r in enumerate(lows, 1):
        cards.append(render_card(i, r, skel.get((r["from"], r["to"], r["rel"])), kind="low"))
    for j, r in enumerate(spots, len(lows) + 1):
        cards.append(render_card(j, r, skel.get((r["from"], r["to"], r["rel"])), kind="spot"))

    by_level = label_data["by_level"]
    total = label_data["count"]
    n_labelers = results[0].get("n_labelers", "?") if results else "?"
    models_seen = sorted({rr["model"] for r in results for rr in r["raw"]})
    n_low = len(lows)
    n_spot = len(spots)

    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>③-C gold 评审 · {n_low} low + {n_spot} 抽查</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font: 14px/1.6 -apple-system,"PingFang SC",sans-serif; margin: 0; background: #f5f7fa; color: #1c2530; }}
.wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 18px 80px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
.sub {{ color: #677381; font-size: 13px; margin-bottom: 16px; }}
.statbar {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 22px; }}
.s {{ background: #fff; border: 1px solid #e1e6ee; border-radius: 8px; padding: 8px 12px; font-size: 12px; }}
.s b {{ font-size: 18px; display: block; margin-top: 2px; color: #1c2530; }}
.warn {{ background: #fff8e1; border: 1px solid #ffd54f; border-radius: 8px; padding: 12px 14px; margin-bottom: 22px; font-size: 13px; }}
.warn b {{ color: #a36500; }}
.card {{ background: #fff; border: 1px solid #e1e6ee; border-radius: 10px; padding: 16px 18px; margin-bottom: 18px; }}
.cardhdr {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }}
.idx {{ background: #1c2530; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
.bdg {{ padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
.bdg.low {{ background: #ffe9e9; color: #9b1c1c; }}
.bdg.spot {{ background: #e8f0fe; color: #1a56db; }}
.rel {{ font-size: 13px; color: #2563eb; font-weight: 600; }}
.strt {{ font-size: 12px; color: #677381; }}
.pids {{ display: flex; align-items: stretch; gap: 12px; margin: 10px 0 6px; }}
.pid {{ flex: 1; background: #f8fafc; border: 1px solid #e6ebf2; border-radius: 6px; padding: 8px 10px; }}
.pid .lbl {{ font-size: 11px; color: #888; }}
.pid code {{ font-size: 12px; color: #0f1419; }}
.pid .t {{ font-size: 13px; margin-top: 4px; color: #2d3748; }}
.arrow {{ display: flex; align-items: center; font-size: 22px; color: #a0aec0; }}
.meta {{ font-size: 12px; color: #677381; margin: 4px 0 10px; }}
.wins {{ display: flex; gap: 10px; margin: 8px 0 10px; }}
.win {{ flex: 1; background: #fafbfd; border: 1px solid #eef1f5; border-radius: 6px; padding: 8px 10px; font-size: 12.5px; }}
.wlbl {{ color: #1a56db; font-weight: 600; font-size: 11px; margin-bottom: 3px; }}
.wbody {{ color: #2d3748; line-height: 1.5; }}
.cons {{ font-size: 12px; color: #4a5568; margin: 8px 0; padding: 4px 8px; background: #f8fafc; border-radius: 4px; }}
table.votes {{ width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12.5px; }}
table.votes th {{ background: #edf2f7; padding: 6px 8px; text-align: left; color: #4a5568; font-size: 11.5px; }}
table.votes td {{ padding: 6px 8px; border-bottom: 1px solid #eef1f5; vertical-align: top; }}
table.votes td.m {{ font-weight: 600; color: #2563eb; width: 60px; }}
table.votes td.d {{ width: 130px; }}
table.votes td.c {{ width: 50px; color: #888; }}
table.votes td.r {{ color: #2d3748; }}
table.votes tr.ok td.d {{ color: #15803d; font-weight: 600; }}
table.votes tr.bad td.d {{ color: #b91c1c; font-weight: 600; }}
table.votes tr.mid td.d {{ color: #a36500; font-weight: 600; }}
.prompt {{ background: #fff7ed; border: 1px solid #fed7aa; border-radius: 6px; padding: 8px 12px; font-size: 13px; color: #9a3412; }}
.prompt b {{ color: #7c2d12; }}
</style></head><body><div class="wrap">
<h1>③-C gold 评审</h1>
<div class="sub">输入:labels_raw.json(Task8 跑回)+ golden_pairs.jsonl(Task7 骨架) · 输出:你裁后我冻 golden_v1.jsonl</div>

<div class="statbar">
  <div class="s">总对数<b>{total}</b></div>
  <div class="s">high(一致)<b>{by_level.get('high', 0)}</b></div>
  <div class="s">mid(2:1)<b>{by_level.get('mid', 0)}</b></div>
  <div class="s">low(分歧)<b>{by_level.get('low', 0)}</b></div>
  <div class="s">failed<b>{by_level.get('failed', 0)}</b></div>
  <div class="s">n_labelers<b>{n_labelers}</b></div>
  <div class="s">实到模型<b>{', '.join(models_seen)}</b></div>
</div>

<div class="warn">
<b>注意:opus 全员未出标(StructuredOutput 失败)</b>,实际只有 sonnet + haiku 两票。
故 high 是"两票一致"、low 是"两票分裂"——<b>mid 这档不存在</b>(2 票天然不可能 2:1)。
本页:<b>{n_low} 个 low 必须你裁</b> + <b>{n_spot} 个 high 抽查兜底</b>。
裁完发我:<code>#1 accept / 理由</code>、<code>#2 reject / 理由</code> ……一行一条即可。
</div>

{''.join(cards)}

</div></body></html>"""
    return doc

def main():
    label_data = load_labels()
    skel = load_skeleton()
    doc = render(label_data, skel)
    OUT_HTML.write_text(doc, encoding="utf-8")
    n_low = sum(1 for r in label_data["results"] if r["agreement"] == "low")
    print(f"评审页已生成: {OUT_HTML}")
    print(f"  total: {label_data['count']} · low(必裁): {n_low}")
    print(f"  by_level: {label_data['by_level']}")

if __name__ == "__main__":
    main()
