"""P0/P1/P2 优先级算法。

打分规则:每命中一个业务线 +3,直辖市 +2,GDP Top 10 +1。
"""
from __future__ import annotations
from typing import Iterable

WEIGHT_PER_BUSINESS = 3
WEIGHT_MUNICIPALITY = 2
WEIGHT_GDP_TOP10 = 1

MUNICIPALITIES = {"北京市", "上海市", "天津市", "重庆市"}

GDP_TOP10_2024 = {
    "上海市", "北京市", "深圳市", "重庆市", "广州市",
    "苏州市", "成都市", "杭州市", "武汉市", "南京市",
}

BUSINESS_RULES = {
    "充电": [
        {"label": "一线", "cities": {"北京市", "上海市", "广州市", "深圳市"}},
        {"label": "新一线", "cities": {
            "成都市", "杭州市", "武汉市", "重庆市", "天津市", "西安市",
            "苏州市", "南京市", "长沙市", "郑州市", "济南市", "合肥市",
            "昆明市", "无锡市", "宁波市", "青岛市", "厦门市", "福州市", "沈阳市",
        }},
    ],
    "加油": [
        {"label": "top50_增量", "cities": {
            "东莞市", "佛山市", "嘉兴市", "温州市", "泉州市",
            "南通市", "烟台市", "潍坊市", "常州市", "惠州市",
        }},
    ],
    "电力": [
        {"label": "省会(去重后)", "cities": {
            "石家庄市", "太原市", "呼和浩特市", "长春市", "哈尔滨市",
            "南昌市", "贵阳市", "拉萨市", "兰州市", "西宁市",
            "银川市", "乌鲁木齐市", "海口市", "南宁市",
        }},
        {"label": "计划单列", "cities": {"大连市"}},
    ],
}


def reasons_for_city(city: str) -> list[str]:
    """城市命中的业务线规则 label,用于审计。"""
    out = []
    for line, rules in BUSINESS_RULES.items():
        for r in rules:
            if city in r["cities"]:
                out.append(f"{line}_{r['label']}")
    return out


def compute_priority_score(city: str, reasons: Iterable[str],
                           is_municipality: "bool | None" = None) -> float:
    reasons = list(reasons)
    if is_municipality is None:
        is_municipality = city in MUNICIPALITIES
    score = len(reasons) * WEIGHT_PER_BUSINESS
    if is_municipality:
        score += WEIGHT_MUNICIPALITY
    if city in GDP_TOP10_2024:
        score += WEIGHT_GDP_TOP10
    return float(score)


def all_p0_cities() -> list[tuple[str, list[str], float]]:
    cities = set()
    for line, rules in BUSINESS_RULES.items():
        for r in rules:
            cities.update(r["cities"])
    out = []
    for c in cities:
        r = reasons_for_city(c)
        s = compute_priority_score(c, r)
        out.append((c, r, s))
    out.sort(key=lambda x: (-x[2], x[0]))
    return out
