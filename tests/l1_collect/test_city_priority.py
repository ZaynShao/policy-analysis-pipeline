"""Tests for city_priority."""
from __future__ import annotations
from scripts.l1_collect.city_priority import (
    compute_priority_score, BUSINESS_RULES, reasons_for_city, all_p0_cities,
)


def test_score_first_tier_charging():
    # 北京:充电(一线)+ 电力(直辖市) → 高分
    score = compute_priority_score(
        city="北京市", reasons=["充电_一线", "电力_直辖市"], is_municipality=True
    )
    assert score >= 8


def test_score_provincial_capital_only():
    score = compute_priority_score(city="贵阳市", reasons=["电力_省会(去重后)"], is_municipality=False)
    assert 3 <= score <= 5


def test_score_zero_reasons():
    score = compute_priority_score(city="某小城", reasons=[], is_municipality=False)
    assert score == 0


def test_business_rules_no_overlap_within_line():
    """同一业务线内规则之间不应重复(避免同城被加两次同类分)。"""
    for line, rules in BUSINESS_RULES.items():
        cities = [c for r in rules for c in r["cities"]]
        assert len(cities) == len(set(cities)), f"重复城市 in {line}"


def test_reasons_for_known_city():
    r = reasons_for_city("北京市")
    assert len(r) >= 1
    assert any("充电" in x for x in r)


def test_all_p0_cities_sorted_desc():
    out = all_p0_cities()
    assert len(out) >= 40
    scores = [x[2] for x in out]
    assert scores == sorted(scores, reverse=True)
