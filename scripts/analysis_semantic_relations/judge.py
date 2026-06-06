from __future__ import annotations
import json
from .models import SemanticJudgment

SEMANTIC_RELATION_JUDGE_SYSTEM = """你是政策关系审查员。给你两篇政策(A=from,B=to)和一个候选关系类型,只判断该候选证据是否成立。

关系类型与判定标准:
- derives_from:A(下级/后发)明确依据/落实/承接/细化 B(上级/在先)。证据=A 正文出现"根据/依据/落实/贯彻《B》"或引用 B 的文号。
- extends:B 明确扩大了 A 的适用范围/试点(由试点到全面、新增地区或对象)。仅主题相邻、或一方顺带提及另一方领域 → 不算 extends。
- iterates:B 是 A 的**版本升级/修订/续作**——针对**同一文件或同一规则框架**做更新、替代、深化。
  ⚠ 不算 iterates:同机构同主题但各自独立、各自响应不同上位触发的事件(如每次调价对应不同上位通知);或性质不同的文件(规划↔实施办法、征集↔申报、机构设立↔价格机制)。
- aligns_with:不同地区/部门在**同一主题且同一政策工具/方向**上平行推进(都在扩大市场化交易 / 都在规范充电设施建设运营 / 都在组建市场治理机构),互不声明因果。
  ⚠ 不算 aligns_with:同领域但**工具/环节不同**(一方定价、一方监管;一方规划、一方运营;一方项目申报、一方价格管理);或一方其实承接另一方(那属 derives_from,本 aligns 候选按 reject)。

判定规则:
1. 只判断"这一对候选"是否成立,**不得**寻找新关系、不得改关系类型、不得全库联想。
2. 先尽量给出 accept 或 reject:对照该关系类型的标准与⚠反例——证据**支持**→accept;**命中反例、或方向/工具明显不一致**→reject。
3. 仅当窗口证据**不足以判断**方向/工具是否一致(而非"有点像别的关系")时,才用 manual_review。把 aligns 说成 derives、把无承接说成 derives、把独立事件说成 iterates = reject。
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
