from __future__ import annotations
import json
from .models import SemanticJudgment

SEMANTIC_RELATION_JUDGE_SYSTEM = """你是政策关系审查员。给你两篇政策和一个候选关系类型,只判断该候选证据是否成立。
关系类型:
- derives_from:A(下级)落实/承接/细化 B(上级)。
- extends:后政策扩大了前政策的范围/试点。
- iterates:同机构同主题的年度续作/版本迭代。
- aligns_with:不同地区或部门在同一主题上方向对齐(不声明因果)。
规则:
1. 你只判断"这一对候选"是否成立,**不得**寻找新关系、不得改关系类型、不得全库联想。
2. 证据不足、模棱两可、或更像别的关系 → decision=manual_review(宁可进人工,不要硬判)。
3. 把 aligns 说成 derives、把无承接说成 derives = reject。
只输出 JSON:{"decision":"accept|reject|manual_review","confidence":0-1,"reason":"一句话"}
"""


def judge_candidate(client, cand: dict, max_tokens: int = 2048) -> SemanticJudgment:
    ev = cand.get("evidence", {})
    user = (f"关系类型:{cand['rel']}\n"
            f"A(from):{ev.get('from_title','')}\nB(to):{ev.get('to_title','')}\n"
            f"证据:from_window={ev.get('from_window','')} to_window={ev.get('to_window','')}\n"
            f"归属:theme_context={ev.get('theme_context',[])} 候选依据={cand.get('candidate_basis',[])}")
    txt = client.complete(system=SEMANTIC_RELATION_JUDGE_SYSTEM, user=user, max_tokens=max_tokens)
    cid = cand.get("candidate_id", f"{cand.get('from')}|{cand.get('to')}|{cand.get('rel')}")
    try:
        d = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        decision = d.get("decision", "manual_review")
        if decision not in {"accept", "reject", "manual_review"}:
            decision = "manual_review"
        return SemanticJudgment(cid, decision, float(d.get("confidence", 0.0)),
                                str(d.get("reason", "")), getattr(client, "model", "unknown"))
    except Exception:
        return SemanticJudgment(cid, "manual_review", 0.0, "judge 返回非JSON", getattr(client, "model", "unknown"))
