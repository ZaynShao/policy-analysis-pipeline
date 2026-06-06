"""③-C preview 人审页:把 accepted 689 条关系做成可翻阅、文字预处理过的审阅页。一次性。

为什么:run 出的 semantic_relation_preview.html / 各 jsonl 信息密、文字带 markdown/URL/导航垃圾,
人类读不动。这里:清洗 from/to 标题 + 证据窗口 → 一卡一关系、键盘翻页、按 rel 过滤、
按置信度升序(最不稳的排前面,从头扫先撞边界对)、可疑行打标。

输入 state/node3c/sem_preview_20260606/accepted_semantic_relations.jsonl
输出 state/node3c/sem_preview_20260606/reports/accepted_review.html
"""
from __future__ import annotations
import json, re, html, os
from pathlib import Path

PREV = Path("state/node3c/sem_preview_20260606")
ACCEPTED = PREV / os.environ.get("ACC_FILE", "accepted_semantic_relations.jsonl")
OUT = PREV / "reports" / os.environ.get("OUT_FILE", "accepted_review.html")

REL_ZH = {
    "derives_from": "derives_from·下位承接上位",
    "extends": "extends·扩大范围/试点",
    "iterates": "iterates·版本迭代",
    "aligns_with": "aligns_with·同主题跨域对齐",
}
# 政策类文书关键词;标题不含任一 → 疑似新闻/动态(上游污染)
DOC_WORDS = ("通知", "方案", "办法", "规则", "意见", "细则", "规划", "计划", "决定",
             "公告", "指引", "措施", "条例", "规定", "实施", "行动")
NEWS_WORDS = ("新闻", "访谈", "接受", "报道", "再迎", "释放", "掀", "热点", "累计",
              "成效", "亿元", "答记者", "新闻办")


def clean_title(t: str) -> str:
    t = t or ""
    t = re.sub(r"\s*[-—]\s*[^-—]*(门户网站|人民政府|发展和改革委员会|政务|网站)\s*$", "", t)
    t = t.replace("# ", "").replace("**", "").strip()
    t = re.sub(r"\s*\.\.\.\s*$", "…", t)
    return t.strip() or "(无标题)"


def clean_window(w: str) -> str:
    w = w or ""
    # markdown 链接 [文字](url) → 文字;裸 (http...) 去掉
    w = re.sub(r"\[([^\]]*)\]\((https?://[^)]*)\)", r"\1", w)
    w = re.sub(r"\(https?://[^)]*\)", "", w)
    w = re.sub(r"https?://\S+", "", w)
    # 去 markdown 标记
    w = w.replace("**", "").replace("##", "").replace("#", "")
    # 去元数据/导航碎片
    for pat in [r"政策原文", r"返回首页", r"网站地图", r"索\s*引\s*号[:：]?\s*\S*",
                r"主题分类[:：]?\S*", r"发文机[关构][:：]?\S*", r"成文日期[:：]?\S*",
                r"发布日期[:：]?\S*", r"发文时间[:：]?\S*", r"发布机构[:：]?\S*",
                r"公开方式[:：]?\S*", r"有效性[:：]?\S*", r"失效时间[:：]?\S*",
                r"文\s*号[:：]?\s*\S*", r"来源[:：]", r"标\s*题[:：]",
                r"中文域名[:：]?\S*", r"\bplan\.\S+", r"\S*\.gov\.cn\S*",
                r"\d{4}[-\s]\d{2}[-\s]\d{2}", r"（无）"]:
        w = re.sub(pat, " ", w)
    w = re.sub(r"[-•|]\s*", " ", w)
    w = re.sub(r"\s+", " ", w).strip()
    return w or "(窗口为空)"


def flags_for(rel, conf, ft, tt):
    # 注:原"疑似新闻/动态"弱flag(缺政策词)假阳性率极高(267/689 误标好政策),已废;
    # 非政策端点改由 finalize_3c_clean 的确定性规则前置剔除。此处只留"低置信"软标。
    fl = []
    if conf is not None and conf < 0.8:
        fl.append("低置信·已人核")
    return fl


def main():
    rows = [json.loads(l) for l in ACCEPTED.read_text(encoding="utf-8").splitlines() if l.strip()]
    items = []
    for r in rows:
        ev = r.get("evidence", {})
        ft, tt = clean_title(ev.get("from_title", "")), clean_title(ev.get("to_title", ""))
        conf = r.get("confidence")
        items.append({
            "from": r["from"], "to": r["to"], "rel": r["rel"],
            "conf": conf,
            "ft": ft, "tt": tt,
            "fw": clean_window(ev.get("from_window", "")),
            "tw": clean_window(ev.get("to_window", "")),
            "basis": " · ".join(r.get("candidate_basis", [])),
            "reason": r.get("judge_reason", ""),
            "flags": flags_for(r["rel"], conf, ft, tt),
        })
    # 默认排序:置信度升序(最不稳在前),次按 rel
    items.sort(key=lambda x: (x["conf"] if x["conf"] is not None else 1, x["rel"]))

    from collections import Counter
    by_rel = Counter(i["rel"] for i in items)
    n_flag = sum(1 for i in items if i["flags"])
    data_json = json.dumps(items, ensure_ascii=False)

    doc = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>③-C accepted 人审(__N__ 条)</title>
<style>
*{box-sizing:border-box}
body{font:15px/1.6 -apple-system,"PingFang SC",sans-serif;margin:0;background:#eef1f6;color:#1c2530}
.top{position:sticky;top:0;background:#fff;border-bottom:1px solid #d7deea;padding:12px 18px;z-index:9}
.top h1{font-size:17px;margin:0 0 8px}
.ctrl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:13px}
.ctrl button{border:1px solid #c3ccdb;background:#f3f6fb;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:13px}
.ctrl button.on{background:#2563eb;color:#fff;border-color:#2563eb}
.ctrl .sp{flex:1}
.stage{max-width:920px;margin:18px auto;padding:0 16px}
.card{background:#fff;border:1px solid #d7deea;border-radius:12px;padding:20px 22px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.cardhd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.pos{font-size:13px;color:#677;font-weight:600}
.rel{background:#e8f0fe;color:#1a56db;border-radius:5px;padding:3px 9px;font-size:13px;font-weight:600}
.conf{border-radius:5px;padding:3px 9px;font-size:13px;font-weight:600}
.flag{background:#fff3cd;color:#8a5a00;border:1px solid #ffe08a;border-radius:5px;padding:2px 8px;font-size:12px}
.pair{display:flex;gap:14px;align-items:stretch;margin:6px 0}
.pol{flex:1;background:#f7f9fc;border:1px solid #e6ecf5;border-radius:8px;padding:12px 14px}
.pol .role{font-size:11px;color:#8a98ad;font-weight:600;letter-spacing:.5px}
.pol .ttl{font-size:15px;font-weight:600;margin:3px 0 6px;color:#16202e}
.pol .pid{font-size:11px;color:#9aa7b8;font-family:ui-monospace,monospace}
.pol .win{font-size:13px;color:#3a4757;margin-top:8px;max-height:8.5em;overflow:auto;line-height:1.55}
.arrow{display:flex;align-items:center;font-size:26px;color:#9aa7b8}
.meta{margin-top:12px;font-size:13px;color:#46546a}
.meta .lab{color:#8a98ad}
.reason{margin-top:8px;background:#f0f7ff;border-left:3px solid #2563eb;padding:8px 12px;border-radius:0 6px 6px 0;font-size:13.5px}
.nav{display:flex;justify-content:space-between;align-items:center;margin-top:16px;font-size:13px;color:#677}
.nav button{border:1px solid #c3ccdb;background:#fff;border-radius:8px;padding:8px 18px;cursor:pointer;font-size:14px}
.hint{color:#8a98ad;font-size:12px;text-align:center;margin-top:8px}
kbd{background:#eef1f6;border:1px solid #c3ccdb;border-radius:4px;padding:0 5px;font-size:11px}
</style></head><body>
<div class="top">
<h1>③-C accepted 人审 · 共 <span id="total">__N__</span> 条(默认按置信度升序:最不稳在前)</h1>
<div class="ctrl">
<button data-rel="all" class="on">全部 __N__</button>
<button data-rel="aligns_with">aligns __ALIGNS__</button>
<button data-rel="derives_from">derives __DERIVES__</button>
<button data-rel="extends">extends __EXTENDS__</button>
<button data-rel="iterates">iterates __ITERATES__</button>
<span class="sp"></span>
<button id="flagonly">只看可疑(__NFLAG__)</button>
<button id="sortdir">置信↑</button>
</div></div>
<div class="stage"><div id="card" class="card"></div>
<div class="nav"><button id="prev">← 上一条</button><span id="counter"></span><button id="next">下一条 →</button></div>
<div class="hint">键盘 <kbd>←</kbd> <kbd>→</kbd> 翻页 · 黄标=可疑(低置信 / 疑似新闻动态),优先核</div>
</div>
<script>
const DATA = __DATA__;
let relF="all", flagOnly=false, asc=true, idx=0;
function view(){
  let v = DATA.filter(d=> (relF==="all"||d.rel===relF) && (!flagOnly||d.flags.length));
  v.sort((a,b)=>{const ca=a.conf??1, cb=b.conf??1; return asc? ca-cb : cb-ca;});
  return v;
}
function confColor(c){ if(c==null)return"#eee"; if(c>=0.9)return"#d8f3e0"; if(c>=0.8)return"#fff3cd"; return"#ffd9d9"; }
function esc(s){const d=document.createElement("div");d.textContent=s==null?"":s;return d.innerHTML;}
function render(){
  const v=view(); if(idx>=v.length)idx=0; if(idx<0)idx=v.length-1;
  const d=v[idx]; const card=document.getElementById("card");
  if(!d){card.innerHTML="<p>无</p>";document.getElementById("counter").textContent="0/0";return;}
  card.innerHTML=`
   <div class="cardhd">
     <span class="pos">#${idx+1}/${v.length}</span>
     <span class="rel">${esc(REL[d.rel]||d.rel)}</span>
     <span class="conf" style="background:${confColor(d.conf)}">置信 ${d.conf??"?"}</span>
     ${d.flags.map(f=>`<span class="flag">${esc(f)}</span>`).join("")}
   </div>
   <div class="pair">
     <div class="pol"><div class="role">FROM</div><div class="ttl">${esc(d.ft)}</div>
       <div class="pid">${esc(d.from)}</div><div class="win">${esc(d.fw)}</div></div>
     <div class="arrow">${d.rel==="aligns_with"?"↔":"→"}</div>
     <div class="pol"><div class="role">TO</div><div class="ttl">${esc(d.tt)}</div>
       <div class="pid">${esc(d.to)}</div><div class="win">${esc(d.tw)}</div></div>
   </div>
   <div class="meta"><span class="lab">候选依据:</span> ${esc(d.basis)}</div>
   <div class="reason"><span class="lab">判官理由:</span> ${esc(d.reason)}</div>`;
  document.getElementById("counter").textContent=`${idx+1} / ${v.length}`;
}
const REL=__RELZH__;
document.querySelectorAll(".ctrl button[data-rel]").forEach(b=>b.onclick=()=>{
  document.querySelectorAll(".ctrl button[data-rel]").forEach(x=>x.classList.remove("on"));
  b.classList.add("on"); relF=b.dataset.rel; idx=0; render();});
document.getElementById("flagonly").onclick=function(){flagOnly=!flagOnly;this.classList.toggle("on",flagOnly);idx=0;render();};
document.getElementById("sortdir").onclick=function(){asc=!asc;this.textContent=asc?"置信↑":"置信↓";idx=0;render();};
document.getElementById("prev").onclick=()=>{idx--;render();};
document.getElementById("next").onclick=()=>{idx++;render();};
document.addEventListener("keydown",e=>{if(e.key==="ArrowLeft"){idx--;render();}if(e.key==="ArrowRight"){idx++;render();}});
render();
</script></body></html>"""
    doc = (doc.replace("__DATA__", data_json).replace("__RELZH__", json.dumps(REL_ZH, ensure_ascii=False))
           .replace("__N__", str(len(items))).replace("__NFLAG__", str(n_flag))
           .replace("__ALIGNS__", str(by_rel.get("aligns_with", 0)))
           .replace("__DERIVES__", str(by_rel.get("derives_from", 0)))
           .replace("__EXTENDS__", str(by_rel.get("extends", 0)))
           .replace("__ITERATES__", str(by_rel.get("iterates", 0))))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"✓ {OUT}")
    print(f"  {len(items)} 条 · 可疑 {n_flag} · by_rel {dict(by_rel)}")


if __name__ == "__main__":
    main()
