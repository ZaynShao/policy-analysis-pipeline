"""②-B Task13:把用户裁决(user_verdicts)+ comprehensive 标记 应用到 proposed_gold,
产出已核验的干净 gold(golden_clean.json,尚未埋错)。一次性。"""
import json
from pathlib import Path

BASE = Path("/Users/shaoziyuan/dev/政策分析-pipeline/state/node2b/golden")
# gold 评审中确认为"大综合政策"的(primary 名义化)
COMPREHENSIVE_PIDS = {"P_2022_GO_6a4cc949", "P_2022_CQ_229620a1", "P_2024_NEA_93_a"}

proposed = json.load(open(BASE / "proposed_gold.json"))
verdicts = {v["pid"]: v for v in json.load(open(BASE / "user_verdicts.json")) if "pid" in v}

clean, changes = [], []
for p in proposed:
    pid = p["pid"]
    g = dict(p["gold"])
    g.setdefault("scores", {})
    g["comprehensive"] = pid in COMPREHENSIVE_PIDS
    v = verdicts.get(pid)
    status = "accepted_unreviewed"
    note = ""
    if v:
        status = v.get("status", "ok")
        note = v.get("note", "")
        corr = v.get("corrections") or {}
        if corr:
            if "themes" in corr: g["themes"] = corr["themes"]
            if "primary_theme" in corr: g["primary_theme"] = corr["primary_theme"]
            if "importance" in corr: g["importance"] = corr["importance"]
            if "scores" in corr:                       # 部分维度合并
                g["scores"] = {**g["scores"], **corr["scores"]}
            changes.append((pid, "verdict改", json.dumps(corr, ensure_ascii=False)))
    if g["comprehensive"]:
        changes.append((pid, "标comprehensive", ""))
    clean.append({
        "pid": pid, "title": p["title"], "level": p["level"], "path": p.get("path", ""),
        "agreement": p["agreement"], "review_status": status, "note": note,
        "gold": {"themes": g["themes"], "primary_theme": g["primary_theme"],
                 "comprehensive": g["comprehensive"], "scores": g["scores"],
                 "importance": g["importance"]},
    })

json.dump(clean, open(BASE / "golden_clean.json", "w"), ensure_ascii=False, indent=2)

print(f"golden_clean.json: {len(clean)} 篇")
from collections import Counter
print("review_status:", dict(Counter(c["review_status"] for c in clean)))
print("comprehensive=true:", [c["pid"] for c in clean if c["gold"]["comprehensive"]])
print("\n应用的改动:")
for pid, kind, detail in changes:
    print(f"  {pid} · {kind} {detail}")
# 自检:每篇 primary ∈ themes(或 themes 空)
bad = [c["pid"] for c in clean if c["gold"]["themes"] and c["gold"]["primary_theme"] not in c["gold"]["themes"]]
print("\n⚠ primary 不在 themes 内:", bad or "无")
