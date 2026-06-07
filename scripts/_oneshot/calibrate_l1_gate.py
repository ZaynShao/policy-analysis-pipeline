"""L1 gate 校准（B类阈值断言）。

跑 gate_one 于全 golden 50，报三数：
  - planted_recall（门）：10 个「最像政策的灰区」非政策被 gate 抓住(label!=policy) ≥ 0.9
  - nonpolicy_recall：全 25 非政策召回
  - policy_precision：25 真政策被正确放行(label==policy)，误杀=被 reject 的真政策

写 state/l1_gate/gate_calibration.json；打印漏网 planted + 误杀 policy 明细，供调 prompt。
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from scripts.l1_collect.policy_gate import gate_one, GoldenRecord
from scripts.common.llm import OpenAICompatClient


def compute_commentary_recall(golden: list, llm_fn) -> float:
    """commentary golden 中 gate action=="commentary" 的比例。golden 为 GoldenRecord 列表。"""
    coms = [r for r in golden if r.gold_label == "commentary"]
    if not coms:
        return 1.0  # vacuous: nothing to miss
    hit = sum(1 for r in coms if gate_one(r.pid, r.url, r.title, r.body_head, llm_fn).action == "commentary")
    return hit / len(coms)


def main() -> None:
    key = os.environ["DEEPSEEK_API_KEY"]
    cli = OpenAICompatClient(
        model=os.environ.get("JUDGE_MODEL", "deepseek-v4-flash"),
        base_url="https://api.deepseek.com", api_key=key,
        log_path="state/l1_gate/calib_calls.jsonl")

    G = [GoldenRecord(**json.loads(l)) for l in
         Path("state/l1_gate/golden/golden_v1.jsonl").read_text(encoding="utf-8").split("\n")
         if l.strip()]
    results = {r.pid: gate_one(r.pid, r.url, r.title, r.body_head, cli.complete) for r in G}

    planted = [r for r in G if r.is_planted]
    nonpol = [r for r in G if r.gold_label == "non_policy"]
    policy = [r for r in G if r.gold_label == "policy"]
    coms = [r for r in G if r.gold_label == "commentary"]

    def caught(r):  # 非政策被抓 = 没当成 policy 放行
        return results[r.pid].label != "policy"

    planted_rec = sum(caught(r) for r in planted) / len(planted)
    nonpol_rec = sum(caught(r) for r in nonpol) / len(nonpol)
    passed = [r for r in policy if results[r.pid].label == "policy"]
    false_reject = [r for r in policy if results[r.pid].action == "reject"]
    precision = len(passed) / len(policy)

    com_hit = [r for r in coms if results[r.pid].action == "commentary"]
    com_miss = [r for r in coms if results[r.pid].action != "commentary"]
    com_rec = len(com_hit) / len(coms) if coms else 1.0

    print(f"planted_recall   : {planted_rec:.2%} ({sum(caught(r) for r in planted)}/{len(planted)})")
    print(f"nonpolicy_recall : {nonpol_rec:.2%} ({sum(caught(r) for r in nonpol)}/{len(nonpol)})")
    print(f"policy_precision : {precision:.2%} (放行 {len(passed)}/{len(policy)}, 误杀 {len(false_reject)})")
    print(f"commentary_recall: {com_rec:.2%} ({len(com_hit)}/{len(coms)})")

    miss = [r for r in planted if not caught(r)]
    if miss:
        print("\n⚠ planted 漏网(被当政策放行):")
        for r in miss:
            print(f"   {results[r.pid].label:18s} conf={results[r.pid].confidence:.2f} "
                  f"{r.title[:40]} [{r.notes}]")
    if false_reject:
        print("\n⚠ 真政策被误杀:")
        for r in false_reject:
            print(f"   {results[r.pid].label:18s} conf={results[r.pid].confidence:.2f} "
                  f"ev={results[r.pid].evidence[:20]} {r.title[:36]}")
    if com_miss:
        print("\n⚠ commentary 漏网(未被识别):")
        for r in com_miss:
            print(f"   {results[r.pid].action:18s} {r.title[:50]}")

    overall_pass = planted_rec >= 0.9 and (not coms or com_rec >= 0.9)
    Path("state/l1_gate/gate_calibration.json").write_text(json.dumps({
        "planted_recall": planted_rec, "nonpolicy_recall": nonpol_rec,
        "policy_precision": precision, "commentary_recall": com_rec,
        "pass": overall_pass,
        "n_golden": len(G), "n_planted": len(planted), "n_commentary": len(coms),
        "planted_miss": [r.pid for r in miss],
        "policy_false_reject": [r.pid for r in false_reject],
        "commentary_miss": [r.pid for r in com_miss],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if not overall_pass:
        reasons = []
        if planted_rec < 0.9:
            reasons.append(f"planted_recall={planted_rec:.2%}")
        if coms and com_rec < 0.9:
            reasons.append(f"commentary_recall={com_rec:.2%}")
        print("\nFAIL — " + ", ".join(reasons) + " 调 policy_gate._SYSTEM/heuristic 重跑(≤4次)")
    else:
        print("\nPASS ✅")


if __name__ == "__main__":
    main()
