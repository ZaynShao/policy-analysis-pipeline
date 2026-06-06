#!/usr/bin/env python3
"""③-C accepted 二次 triage(确定性·preview 内·不写 vault/raw)。

为什么:人审页把 357 条涂黄,但 95% 是 flag 设计烂——
  A 端点是非政策文书(人大答复/提案/座谈/解读/动态/新闻)= 规则可判死,不该上人眼;
  B "标题缺政策词" 弱 flag 假阳性爆炸(大多是好政策);
  C 真低置信(<0.8、两端都政策)才要人看。
本脚本:用高精度"非政策端点"规则把 A 剔出 accepted(记 B7 回灌 L1),
删 B 弱 flag,析出 C 残量供人核。**只动 preview 产物,不碰 vault/raw**。

规则定位:这是常驻通则(非政策文书不能当政策↔政策关系端点),验证后该固化进 program_gate;
此处先在 oneshot 层验精度。

输入  state/node3c/sem_preview_20260606/accepted_semantic_relations.jsonl
输出  同目录 accepted_clean.jsonl / dropped_nonpolicy.jsonl / residual_review.jsonl + 控制台清单
"""
from __future__ import annotations
import json, re
from collections import Counter
from pathlib import Path

PREV = Path("state/node3c/sem_preview_20260606")
ACCEPTED = PREV / "accepted_semantic_relations.jsonl"

# 高精度"非政策端点"标记:命中=该端点根本不是一份政策文件。
# 设计取向:宁可漏(残量我再扫),不可误杀真政策——所以只收**明确**非政策的复合词,
# 不收裸"建议/意见/落地/调研"等可能出现在真政策标题里的歧义词。
NONPOLICY = (
    "部门动态", "_动态", "工作动态", "工作信息", "工作推进", "政策解读", "文字解读", "图解",
    "政策问答", "答记者问", "答复函", "复函", "答复的函", "答复意见", "答复",
    "号建议", "建议办理", "建议答复", "建议公开", "代表建议", "人大建议",
    "号提案", "提案答复", "提案的答复", "提案答复的函", "提案", "届人大", "届委员会", "次会议",
    "座谈会", "新闻发布会", "通气会", "框架协议", "强强联合", "成功落地",
    "正式揭牌", "正式挂牌", "签约仪式", "答问", "致辞", "讲话", "调研报告",
    "调研进行时", "工作综述", "工作情况的报告", "工作报告", "情况介绍", "专访",
    "综述", "访谈", "知识库", "法规网", "资讯",
)
# 新闻/动态稿的通用形态(非政策文书):标题里有时间戳/感叹号/新闻栏目分隔符/"成效显著"等。
# 这是通用模式(非 pid 硬编码)。
import re as _re
NEWS_RE = _re.compile(r"\d{4}年\s?\d{1,2}月\d{1,2}日|\d{1,2}:\d{2}|成效(显著|明显)|[！]|丨")


def clean(t: str) -> str:
    t = t or ""
    t = re.sub(r"\s*[-—]\s*[^-—]*(门户网站|人民政府|发展和改革委员会|政务|网站)\s*$", "", t)
    return t.replace("# ", "").replace("**", "").strip()


def nonpolicy_hit(t: str) -> str | None:
    for m in NONPOLICY:
        if m in t:
            return m
    if NEWS_RE.search(t):
        return "新闻稿形态(时间戳/感叹号/栏目符/成效)"
    return None


def main():
    rows = [json.loads(l) for l in ACCEPTED.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept, dropped, residual = [], [], []
    drop_markers = Counter()
    for r in rows:
        ev = r.get("evidence", {})
        ft, tt = clean(ev.get("from_title", "")), clean(ev.get("to_title", ""))
        hf, ht = nonpolicy_hit(ft), nonpolicy_hit(tt)
        if hf or ht:
            bad_side = "from" if hf else "to"
            bad_title = ft if hf else tt
            r2 = dict(r)
            r2["_drop_reason"] = f"非政策端点({bad_side}: 命中「{hf or ht}」)"
            r2["_drop_title"] = bad_title
            dropped.append(r2)
            drop_markers[hf or ht] += 1
            continue
        kept.append(r)
        if (r.get("confidence") or 1) < 0.8:
            residual.append({
                "from": r["from"], "to": r["to"], "rel": r["rel"],
                "conf": r.get("confidence"),
                "ft": ft, "tt": tt,
                "fw": (ev.get("from_window", "") or "")[:240],
                "tw": (ev.get("to_window", "") or "")[:240],
                "basis": " · ".join(r.get("candidate_basis", [])),
                "reason": r.get("judge_reason", ""),
            })

    for path, data in [("accepted_clean.jsonl", kept),
                       ("dropped_nonpolicy.jsonl", dropped),
                       ("residual_review.jsonl", residual)]:
        with (PREV / path).open("w", encoding="utf-8") as f:
            for x in data:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")

    print(f"accepted 原 {len(rows)} → clean {len(kept)} · dropped(非政策端点) {len(dropped)} · 残量低置信 {len(residual)}")
    print(f"\n=== 剔除标记分布 ===")
    for m, c in drop_markers.most_common():
        print(f"  「{m}」 × {c}")
    print(f"\n=== 剔除名单(去重端点标题, 供精度核验)===")
    seen = set()
    for d in dropped:
        key = (d["_drop_title"][:50])
        if key in seen:
            continue
        seen.add(key)
        print(f"  [{d['_drop_reason']}] {d['_drop_title'][:60]}")
    print(f"\n=== 残量({len(residual)} 条低置信·两端都像政策·我要逐条核)===")
    for i, x in enumerate(residual, 1):
        print(f"\n#{i} [{x['rel']} conf={x['conf']}] {x['from']} → {x['to']}")
        print(f"   FROM: {x['ft'][:55]}")
        print(f"   TO  : {x['tt'][:55]}")
        print(f"   依据: {x['basis']}")
        print(f"   判官: {x['reason']}")


if __name__ == "__main__":
    main()
