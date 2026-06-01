from .generator import parse_json_block
from .models import JudgeVerdict

JUDGE_SYSTEM = """你是独立第三方审查员,审查另一模型给政策做的归属(theme+分+影响分析)。
只挑语义错:theme 漏挂/错挂、分数明显不合理、影响分析对零相关政策硬写(幻觉)或该写没写。
不挑格式(已有程序门管)。默认严格:拿不准且像错 → reject。
只输出 JSON:{"verdict":"accept|reject","dim":"theme|score|impact|overall","reason":"一句话","confidence":0-1}
"""

def judge_draft(client, rec_title: str, rec_body: str, draft) -> JudgeVerdict:
    user = (f"政策标题:{rec_title}\n正文(节选):\n{rec_body[:1500]}\n\n"
            f"待审归属:themes={draft.themes} primary={draft.primary_theme} "
            f"scores={draft.scores.to_dict()} 重要性={draft.importance} "
            f"影响分析={draft.影响分析}")
    # 256 对 reasoning 模型(judge 可能是 Qwen 等)太小,思考会吃光预算→空;给足裁决头寸。
    txt = client.complete(system=JUDGE_SYSTEM, user=user, max_tokens=1024)
    try:
        d = parse_json_block(txt)
    except Exception:
        return JudgeVerdict(verdict="reject", dim="overall",
                            reason="judge 返回非JSON", confidence=0.0)
    return JudgeVerdict(verdict=d.get("verdict","reject"), dim=d.get("dim","overall"),
                        reason=d.get("reason",""), confidence=float(d.get("confidence",0.0)))
