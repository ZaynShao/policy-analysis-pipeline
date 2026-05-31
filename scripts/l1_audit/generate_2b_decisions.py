"""由 batch_*.jsonl(我逐批分类结果)生成 2b apply 决策文件(只读)。
规则:地方 id_short=省码(决策A);national=部委码;残留重复→dedup;noise→archive;
market_intel→manifest;commentary→defer。new_id 仅换 issuer_short 段(保留 year+hash)。"""
from __future__ import annotations
import json, glob
from pathlib import Path

REVIEW = "/Users/shaoziyuan/dev/政策分析-pipeline/state/source_ready/go_sc_review"

# 省/直辖市/自治区 2 字母码;省名优先,城市名兜底(城市→所在省码)
PROV = {
    "北京": "BJ", "上海": "SH", "天津": "TJ", "重庆": "CQ",
    "广东": "GD", "浙江": "ZJ", "江苏": "JS", "山东": "SD", "河南": "HA", "河北": "HE",
    "山西": "SX", "四川": "SC", "福建": "FJ", "湖南": "HN", "湖北": "HB", "安徽": "AH",
    "江西": "JX", "广西": "GX", "新疆": "XJ", "宁夏": "NX", "内蒙古": "NM", "甘肃": "GS",
    "辽宁": "LN", "吉林": "JL", "黑龙江": "HL", "云南": "YN", "贵州": "GZ", "陕西": "SN",
    "青海": "QH", "海南": "HI", "西藏": "XZ",
    # 城市兜底(true_region 无省前缀时)
    "广州": "GD", "深圳": "GD", "成都": "SC", "武汉": "HB", "南京": "JS", "常州": "JS",
    "苏州": "JS", "盐城": "JS", "杭州": "ZJ", "济南": "SD", "邯郸": "HE", "唐山": "HE",
    "郑州": "HA", "平顶山": "HA", "宁德": "FJ", "厦门": "FJ", "柳州": "GX", "桂林": "GX",
    "梧州": "GX", "南宁": "GX", "贺州": "GX", "崇左": "GX", "贵港": "GX", "银川": "NX",
    "抚顺": "LN", "鄂尔多斯": "NM", "乌海": "NM", "包头": "NM", "呼和浩特": "NM", "赤峰": "NM",
    "太原": "SX", "陵川": "SX", "交口": "SX", "信丰": "JX", "靖远": "GS", "无极": "HE",
    "惠民": "SD", "新邵": "HN", "可克达拉": "XJ", "西夏": "NX", "白银": "GS", "海口": "HI",
}
# 省名优先匹配顺序(长名在前,避免子串误命中)
ORDER = sorted(PROV.keys(), key=len, reverse=True)

# 残留重复:move_pid -> keep_pid(keep 走其本类处置;move 迁 _duplicates)
DEDUP = {
    "P_2023_GO_93548e55": "P_2022_GO_0ae1a2cc",
    "P_2023_GO_bd301e4d": "P_2023_GO_1b2358a4",
    "P_2025_GO_a0bf1352": "P_2025_GO_3560eda4",
    "P_2025_GO_fc24f456": "P_2025_GO_1009d2cd",
    "P_2025_GO_33651c82": "P_2025_SC_cc687c4e",
    "P_2026_GO_55dd902a": "P_2026_GO_d2e50b48",
    "P_2048_GO_4c4555f6": "P_2025_GO_efca57ff",
}
# date 损坏需改年的特例:pid -> (fixed_year, date_fix)
YEAR_FIX = {"P_2027_GO_572b0ea8": ("2023", "2023-09")}


def prov_code(region: str) -> str | None:
    for k in ORDER:
        if k in region:
            return PROV[k]
    return None


def new_id_for(pid: str, short: str, year_override: str | None = None) -> str:
    parts = pid.split("_")  # P_<year>_<short...>_<suffix>
    year = year_override or parts[1]
    suffix = parts[-1]
    return f"P_{year}_{short}_{suffix}"


def main() -> None:
    rows = []
    for f in sorted(glob.glob(f"{REVIEW}/batch_*.jsonl")):
        if "input" in f:
            continue
        rows += [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]

    dec = {"date": "2026-05-31", "rule": "地方=省码(A);national=部委码;只换issuer_short段,保留year+hash",
           "remint": [], "archive": [], "dedup": [], "market_intel": [], "commentary_defer": [],
           "unresolved": []}

    for m, k in DEDUP.items():
        dec["dedup"].append({"move": m, "keep": k})
    moved = set(DEDUP)

    for r in rows:
        pid = r["pid"]
        if pid in moved:
            continue
        cls = r["class"]
        if cls == "noise":
            dec["archive"].append({"pid": pid, "reason": r["evidence"][:80]})
        elif cls == "market_intel":
            dec["market_intel"].append({"pid": pid, "title_evidence": r["evidence"][:80]})
        elif cls == "commentary":
            dec["commentary_defer"].append({"pid": pid, "note": r["evidence"][:80]})
        elif cls == "policy":
            if r["level"] == "national":
                short = r["proposed_id_short"]
            else:
                short = prov_code(r["true_region"])
            if not short or short.startswith("LOCAL"):
                dec["unresolved"].append({"pid": pid, "region": r["true_region"], "proposed": r["proposed_id_short"]})
                continue
            yo = YEAR_FIX.get(pid)
            entry = {"pid": pid, "new_id": new_id_for(pid, short, yo[0] if yo else None),
                     "id_short": short, "true_issuer": r["true_issuer"], "true_region": r["true_region"]}
            if yo:
                entry["date_fix"] = yo[1]
            dec["remint"].append(entry)

    out = Path(REVIEW) / "phase2_2b_decisions.json"
    out.write_text(json.dumps(dec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    print(f"remint={len(dec['remint'])} archive={len(dec['archive'])} dedup={len(dec['dedup'])} "
          f"market_intel={len(dec['market_intel'])} commentary_defer={len(dec['commentary_defer'])} "
          f"unresolved={len(dec['unresolved'])}")
    total = len(dec['remint']) + len(dec['archive']) + len(dec['dedup']) + len(dec['market_intel']) + len(dec['commentary_defer']) + len(dec['unresolved'])
    print(f"total accounted (excl dedup-keeps): {total} (+{len(moved)} dedup-moves already in dedup) ")
    from collections import Counter
    print("remint id_short:", dict(Counter(e['id_short'] for e in dec['remint'])))
    if dec["unresolved"]:
        print("UNRESOLVED:", dec["unresolved"])


if __name__ == "__main__":
    main()
