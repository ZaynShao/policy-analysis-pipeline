"""从 registry + scoring.yaml + decision_framework 构建提示词。"""

def pass1_system(registry, scoring_text: str) -> str:
    theme_lines = "\n".join(
        f"  - {tid}({registry.zh[tid]}):{'/'.join(registry.aliases[tid])}"
        for tid in registry.ids)
    return f"""你是政策归属分析助手。任务:给一篇政策挂主题(theme)并打六维分。

【可选 theme(只能从下列 id 里选,不许造新的)】
{theme_lines}

【挂 theme 规则】
- 挂上所有真正命中的 theme(不限数量);政策跨多主题就都挂。
- 再从挂上的里选 1 个 primary_theme(最核心的那个)。
- 上面每个 theme 后的词是关键词锚,命中可作信号;但以语义为准,不是出现关键词就必挂。
- comprehensive:若政策横跨多主题且**无单一中心**(综合/纲领性,如"XX高质量发展实施方案""XX建设总体方案"),置 true(primary 仍选一个**名义**主书架);否则 false。

【六维打分(0-5,定义见下)】
{scoring_text}

【过期政策】若政策文本标明已失效/废止/有效期已过,D2(直接影响度)按"无现行约束力"打低(1-2);theme 照常挂、D1 据相关度照打——重要性会自然封顶。

只输出 JSON,无解释:
{{"themes":["id1","id2"],"primary_theme":"id1","comprehensive":false,"scores":{{"D1":0,"D2":0,"D3":0,"D4":0,"D5":0,"D6":0}}}}
"""

def pass1_user(rec) -> str:
    region = (rec.raw_fm.get("region") or {})
    return (f"标题:{rec.title}\n发文机构:{'、'.join(rec.issuer)}\n"
            f"层级:{region.get('level','')}\n正文(节选):\n{rec.body_head}")

def pass2_system() -> str:
    return """你是政策业务影响分析助手。服务对象:公司决策层,三业务=加油/充电/电力(储能·VPP·V2G·电力交易)。
就这一篇政策,写 3-key 影响分析 + 行动建议。影响分析必须且只能这三个键。行动建议动词用"趁早"不用"立即"。
只输出 JSON,无解释:
{"影响分析":{"加油":"...","充电":"...","电力_储能_V2G_交易":"..."},"行动建议":["A 趁早:...","B 研究:..."],"didi_impact_one_liner":"..."}
"""

def pass2_user(rec, draft) -> str:
    region = (rec.raw_fm.get("region") or {})
    return (f"标题:{rec.title}\n层级:{region.get('level','')}\n"
            f"已判主题:{draft.themes}\n重要性:{draft.importance}\n正文(节选):\n{rec.body_head}")
