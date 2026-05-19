"""Tests for metadata_extractor."""
from __future__ import annotations
from scripts.l1_collect.metadata_extractor import (
    extract_official_number, extract_date, extract_issuer_from_url,
)


def test_extract_official_number_standard():
    s = "...本通知...（发改能源〔2024〕1128号）规定..."
    assert extract_official_number(s) == "发改能源〔2024〕1128号"


def test_extract_official_number_square_brackets():
    s = "依据沪发改[2023]58号文..."
    out = extract_official_number(s)
    assert "[2023]58号" in out or "〔2023〕58号" in out


def test_extract_date_from_url_pattern():
    assert extract_date("https://www.gov.cn/zhengce/2024-08/15/content_xxx.html") == "2024-08-15"


def test_extract_date_from_body_chinese():
    body = "...本通知自2025年3月1日起施行..."
    assert extract_date("", body=body) == "2025-03-01"


def test_extract_issuer_from_url_ndrc():
    assert extract_issuer_from_url("https://www.ndrc.gov.cn/xxgzz/zcfb/") == "国家发展和改革委员会"


def test_extract_issuer_from_url_unknown():
    assert extract_issuer_from_url("https://unknown.example.com/x") is None
