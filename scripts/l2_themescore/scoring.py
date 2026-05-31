"""确定性算分,规则源 _meta/framework/scoring.yaml。纯函数,零 LLM。"""

def importance(scores) -> int:
    return round(scores.D1 * 0.40 + scores.D2 * 0.40 + scores.D3 * 0.20)

def action_class(scores) -> str:
    urgent = scores.D4 >= 4
    hands_on = scores.D5 >= 4
    base = ("A" if hands_on else "B") if urgent else ("C" if hands_on else "D")
    order = ["A", "B", "C", "D"]
    i = order.index(base)
    if scores.D6 >= 4:
        i = max(0, i - 1)
    elif scores.D6 <= 2:
        i = min(len(order) - 1, i + 1)
    return order[i]

def gate_passed_deep(importance_val: int, region_level: str) -> bool:
    return importance_val >= 3 or region_level in ("国家", "省")

_OPPORTUNITY_THEMES = {"power_market","vpp_theme","v2g","green_power_trading_theme",
                       "energy_storage_theme","aggregator_access","distribution_grid_opening"}
_COMPLIANCE_THEMES  = {"petroleum_retail_compliance","carbon_market_theme"}
_MOAT_THEMES        = {"residential_charging","charging_infra","gas_station_transition_theme"}

def value_tags(importance_val: int, themes: list) -> list:
    tags = []
    ts = set(themes or [])
    if ts & _COMPLIANCE_THEMES:               tags.append("合规")
    if ts & _OPPORTUNITY_THEMES:              tags.append("机会")
    if ts & _MOAT_THEMES and importance_val >= 3: tags.append("壁垒")
    if importance_val <= 3 and not tags:      tags.append("趋势")
    return tags or ["趋势"]
