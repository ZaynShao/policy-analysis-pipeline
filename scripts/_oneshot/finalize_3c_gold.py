"""③-C Task8 收尾:合成 golden_v1.jsonl(冻结的校准真值集)。一次性。

gold_decision 三个来源:
  - high 共识(sonnet+haiku 一致): 取 consensus.decision
  - low(分歧,用户人工裁): 取 USER_VERDICTS(按 (from,to,rel) 键)
  - planted(埋错): reject(golden_pairs 已标 is_planted)

输入:
  state/node3c/golden/golden_pairs.jsonl   —— 骨架(45 行,含刷新后的窗口)
  state/node3c/golden/labels_raw.json      —— Task8 多模型标注
输出:
  state/node3c/golden/golden_v1.jsonl      —— 45 行,每行带 gold_decision + 出处审计

注意(诚实披露,写进 notes):本轮 opus 全员 StructuredOutput 失败,
n_labelers=2(sonnet+haiku);high=两票一致、low=两票分裂,无 mid 档。
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter

BASE = Path("/Users/shaoziyuan/dev/政策分析-pipeline/state/node3c/golden")
PAIRS = BASE / "golden_pairs.jsonl"
LABELS = BASE / "labels_raw.json"
OUT = BASE / "golden_v1.jsonl"
NOTES = BASE / "golden_v1_notes.md"

# 用户对 7 个 low 的人工裁决(2026-06-06,逐条读全文裁),键=(from,to,rel)
USER_VERDICTS = {
    ("P_2017_GD_70875d73", "P_2015_NEA_73", "derives_from"): "accept",        # #1 广州2017 真承接国办发73号
    ("P_2019_HA_6e13fc6b", "P_2015_NDRC_3d821d6e", "derives_from"): "reject",  # #2 河南2019 与9号配套通知是兄弟非父子
    ("P_2012_BJ_466935e2", "P_2015_BJ_c5505b70", "iterates"): "reject",        # #3 两次独立批转不同发改电号,非迭代
    ("P_2016_AH_ae5294fd", "P_2017_GZ_f47663f2", "aligns_with"): "accept",     # #4 同主题跨域对齐
    ("P_2016_AH_ae5294fd", "P_2017_LN_54de50fa", "aligns_with"): "accept",     # #5 安徽 aligns 辽宁(多对齐合法)
    ("P_2017_CQ_c8d99857", "P_2018_HI_bdeeb7db", "aligns_with"): "reject",     # #6 增量配电不同子议题,不对齐
    ("P_2017_GD_70875d73", "P_2017_HI_dcd17e5c", "aligns_with"): "accept",     # #7 同主题(充电基建)跨省对齐
}


def read_jsonl(path):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def main():
    pairs = read_jsonl(PAIRS)
    label_data = json.loads(LABELS.read_text(encoding="utf-8"))
    labels = {(r["from"], r["to"], r["rel"]): r for r in label_data["results"]}

    used_user_keys = set()
    out_rows = []
    src_counter = Counter()
    dec_counter = Counter()

    for p in pairs:
        key = (p["from"], p["to"], p["rel"])
        is_planted = bool(p.get("is_planted"))

        if is_planted:
            gold = "reject"
            source = "planted"
            n_labelers = 0
            raw_votes = None
        elif key in USER_VERDICTS:
            gold = USER_VERDICTS[key]
            source = "user_adjudicated"
            used_user_keys.add(key)
            lbl = labels.get(key)
            n_labelers = lbl.get("n_labelers") if lbl else None
            raw_votes = [{"model": rr["model"], "decision": rr["decision"]} for rr in lbl["raw"]] if lbl else None
        else:
            lbl = labels.get(key)
            if not lbl:
                raise SystemExit(f"✗ 真实对在 labels 中找不到: {key}")
            if lbl["agreement"] == "low":
                raise SystemExit(f"✗ low 对未在 USER_VERDICTS 里裁: {key}")
            gold = lbl["consensus"]["decision"]
            source = "high_consensus"
            n_labelers = lbl.get("n_labelers")
            raw_votes = [{"model": rr["model"], "decision": rr["decision"]} for rr in lbl["raw"]]

        row = dict(p)  # 保留 from/to/rel/stratum/is_planted/planted_error_type/标题/窗口/candidate_basis
        row["gold_decision"] = gold
        row["label_source"] = source
        row["n_labelers"] = n_labelers
        row["raw_votes"] = raw_votes
        out_rows.append(row)
        src_counter[source] += 1
        dec_counter[gold] += 1

    # 校验
    missing = set(USER_VERDICTS) - used_user_keys
    if missing:
        raise SystemExit(f"✗ 有 USER_VERDICTS 键没匹配到任何行: {missing}")
    assert len(out_rows) == 45, f"应 45 行, 得 {len(out_rows)}"
    for r in out_rows:
        assert r["gold_decision"] in {"accept", "reject", "manual_review"}, r
        assert r["from_window"] and r["to_window"], f"窗口空: {r['from']}|{r['to']}"

    with OUT.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # notes(诚实披露)
    real = [r for r in out_rows if not r["is_planted"]]
    planted = [r for r in out_rows if r["is_planted"]]
    real_acc = sum(1 for r in real if r["gold_decision"] == "accept")
    real_rej = sum(1 for r in real if r["gold_decision"] == "reject")
    notes = f"""# ③-C golden_v1 冻结说明 (2026-06-06)

## 规模
- 总 45 行 = 真实 {len(real)} + 埋错 {len(planted)}
- gold_decision 分布: {dict(dec_counter)}
- 真实对: accept {real_acc} / reject {real_rej}
- 出处: {dict(src_counter)}

## ⚠ 诚实披露
1. **opus 全员 StructuredOutput 失败**,本轮 n_labelers=2(sonnet+haiku)。
   high = 两票一致、low = 两票分裂,**无 mid(2:1)档**。换强模型重跑可整体修正(整文件重生)。
2. **规则过度生成**:28 个 high 里 22 个被两模型一致 reject(extends 锚词太松、
   iterates 不分文件性质、aligns 未排除实为 derives 的)。golden 的 25/45 reject 由此而来——
   这是**有难度的测试集**(judge 须否掉规则误报+埋错、留住真 accept),不是 golden 的 bug。
   规则精度是否回头收紧 → 待校准看 judge 能否兜住再定(记 backlog)。

## 校准读法
- `planted_recall ≥ 0.9` = spec §13 达标线(只管 {len(planted)} 个埋错)。
- `agreement`(verdict==gold_decision 全量比对)= 更关键,衡量是否过度接受 25 个 reject。
  见谁都 accept 的 judge: real_accept_kept≈1 但 agreement≈{real_acc}/{len(real)}≈{real_acc/len(real):.2f},一眼穿帮。
"""
    NOTES.write_text(notes, encoding="utf-8")

    print(f"✓ 冻结: {OUT}")
    print(f"  45 行 = 真实 {len(real)}(accept {real_acc}/reject {real_rej}) + 埋错 {len(planted)}")
    print(f"  出处: {dict(src_counter)}")
    print(f"  gold 分布: {dict(dec_counter)}")
    print(f"  notes: {NOTES}")


if __name__ == "__main__":
    main()
