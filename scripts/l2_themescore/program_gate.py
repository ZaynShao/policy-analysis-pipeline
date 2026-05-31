from .scoring import importance, action_class

IMPACT_KEYS = {"加油", "充电", "电力_储能_V2G_交易"}

def check_draft(d, valid_ids) -> list:
    """单篇程序门。返回违规列表(空=过)。"""
    v = []
    if not d.themes:
        v.append("结构:themes 为空")
    if d.primary_theme not in (d.themes or []):
        v.append("结构:primary_theme 不在 themes 内")
    bad = [t for t in (d.themes or []) if t not in valid_ids]
    if bad:
        v.append(f"registry:未知 theme {bad}")
    if d.importance != importance(d.scores):
        v.append(f"公式:重要性 {d.importance} != 重算 {importance(d.scores)}")
    if d.action_class != action_class(d.scores):
        v.append(f"公式:行动分类 {d.action_class} != 重算 {action_class(d.scores)}")
    if d.影响分析 is not None and set(d.影响分析.keys()) != IMPACT_KEYS:
        v.append(f"影响分析键:{sorted(d.影响分析.keys())} != {sorted(IMPACT_KEYS)}")
    has_deep = bool(d.影响分析) and bool(d.行动建议)
    if has_deep != d.gate_passed_deep:
        v.append(f"深档:有深档={has_deep} 但 gate={d.gate_passed_deep}")
    return v

def check_distribution(drafts, n_themes: int) -> list:
    """语料级分布门。返回告警列表。"""
    warns = []
    if not drafts:
        return ["分布:无草稿"]
    overstuffed = [d.pid for d in drafts if len(d.themes or []) >= n_themes]
    if overstuffed:
        warns.append(f"分布:{len(overstuffed)} 篇挂满全部 theme(过挂信号){overstuffed[:5]}")
    islands = [d.pid for d in drafts if not d.themes]
    if islands:
        warns.append(f"分布:{len(islands)} 篇 0 theme(孤岛)")
    return warns
