#!/usr/bin/env python3
"""③-C accepted 终态固化(preview 内·不写 vault/raw)。

链:rule_clean(triage 规则剔非政策端点)→ 再减去人工核出的 4 条残量drop(都是端点仍非政策/坏数据)
   → accepted_clean_final.jsonl。同时:
   - 析出 3 条"工具/主题是否一致"的硬边界 → user_pending(交用户终裁);
   - 把全部剔除端点(规则145 + 人工4)去重成 L1 污染名单 → b7_contamination.jsonl(回灌 L1)。

⚠ HAND_DROP / USER_PENDING 是**本 preview 人工核验的一次性钉快照**(类比 golden 标注),
   不是流水线规则,不进 program_gate;流水线判官/程序门保持零 pid。
"""
from __future__ import annotations
import json
from pathlib import Path
from scripts._oneshot.triage_3c_accepted import clean, nonpolicy_hit

PREV = Path("state/node3c/sem_preview_20260606")
ACCEPTED = PREV / "accepted_semantic_relations.jsonl"

# 人工核 20 条低置信残量后的裁定(by from|to|rel)。仅本 preview 快照。
HAND_DROP = {
    ("P_2019_HA_1be4e1ce", "P_2020_SH_39_b"): "FROM为建议答复(judge认定)·对齐顶层国规属噪声",
    ("P_2021_BJ_927cc52e", "P_2022_SD_67a335e9"): "两端均为新闻特稿(碳账本北京模式/碳市场成效报道)",
    ("P_2022_HE_182d4944", "P_2025_JX_b6890180"): "FROM标题仅剩机构名=L1抽取失败,无法核验端点",
    ("P_2025_GO_1201e389", "P_2026_SN_ab3d416b"): "TO为征求意见稿公告(草稿征集),非成稿政策",
}
# 上述 3 条交用户终裁,结果均=剔除(2026-06-06)。它们是真政策、仅弱aligns被否,
# 不算非政策污染→不进 B7。
WEAK_REL_DROP = {
    ("P_2020_SH_d3a442c8", "P_2021_GD_e369bf1c"): "用户终裁:成品油市场监管vs税控技术,工具不同",
    ("P_2024_HI_e92db1eb", "P_2025_HA_57f372bd"): "用户终裁:代理购电vs上网电价,环节不同+A证据空壳",
    ("P_2025_SH_61", "P_2026_SD_0401ca27"): "用户终裁:综合碳达峰vs专项新能源消纳,主题非同一",
}


def key(r):
    return (r["from"], r["to"], r["rel"])


def main():
    rows = [json.loads(l) for l in ACCEPTED.read_text(encoding="utf-8").splitlines() if l.strip()]
    final, rule_dropped, hand_dropped, weak_dropped = [], [], [], []
    contam = {}  # pid -> {title, marker}

    def note_contam(pid, title, marker):
        if pid not in contam:
            contam[pid] = {"pid": pid, "title": title[:80], "marker": marker}

    for r in rows:
        ev = r.get("evidence", {})
        ft, tt = clean(ev.get("from_title", "")), clean(ev.get("to_title", ""))
        hf, ht = nonpolicy_hit(ft), nonpolicy_hit(tt)
        if hf or ht:
            rule_dropped.append(r)
            if hf:
                note_contam(r["from"], ft, hf)
            if ht:
                note_contam(r["to"], tt, ht)
            continue
        k2 = (r["from"], r["to"])
        if k2 in HAND_DROP:
            r2 = dict(r); r2["_hand_drop"] = HAND_DROP[k2]
            hand_dropped.append(r2)
            # 人工drop里 #1/#3/#5/#18:污染端点也回灌(建议答复/新闻/坏抽取/草稿)
            note_contam(r["from"], ft, "人工核:" + HAND_DROP[k2])
            continue
        if k2 in WEAK_REL_DROP:
            r2 = dict(r); r2["_weak_drop"] = WEAK_REL_DROP[k2]
            weak_dropped.append(r2)  # 真政策·弱aligns被否→剔关系,不进B7
            continue
        final.append(r)

    def dump(name, data):
        with (PREV / name).open("w", encoding="utf-8") as f:
            for x in data:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")

    dump("accepted_clean_final.jsonl", final)
    dump("hand_dropped.jsonl", hand_dropped)
    dump("weak_rel_dropped.jsonl", weak_dropped)
    dump("b7_contamination.jsonl", list(contam.values()))

    print(f"原 accepted {len(rows)}")
    print(f"  规则剔除(非政策端点)   : {len(rule_dropped)}")
    print(f"  人工剔除(非政策残量)   : {len(hand_dropped)}")
    print(f"  用户终裁剔除(弱aligns) : {len(weak_dropped)}")
    print(f"  → clean_final          : {len(final)}")
    print(f"  B7 污染端点(去重pid)   : {len(contam)} → b7_contamination.jsonl")


if __name__ == "__main__":
    main()
