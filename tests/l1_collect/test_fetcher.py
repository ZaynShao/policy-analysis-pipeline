"""Tests for fetcher (all external calls mocked)."""
from __future__ import annotations
from unittest.mock import patch
from scripts.l1_collect.fetcher import fetch_article


@patch("scripts.l1_collect.fetcher._fetch_via_trafilatura")
@patch("scripts.l1_collect.fetcher._fetch_via_firecrawl")
def test_firecrawl_success_short_circuits(mock_fire, mock_traf):
    mock_fire.return_value = "正文内容 > 200 字..." * 10
    r = fetch_article("https://x.gov.cn/a")
    assert r.via == "firecrawl"
    mock_traf.assert_not_called()


@patch("scripts.l1_collect.fetcher._fetch_via_bs4")
@patch("scripts.l1_collect.fetcher._fetch_via_trafilatura")
@patch("scripts.l1_collect.fetcher._fetch_via_firecrawl")
def test_fallback_to_trafilatura(mock_fire, mock_traf, mock_bs):
    mock_fire.return_value = None
    mock_traf.return_value = "trafilatura extracted body" * 20
    r = fetch_article("https://x.gov.cn/a")
    assert r.via == "trafilatura"
    mock_bs.assert_not_called()


@patch("scripts.l1_collect.fetcher._fetch_via_bs4")
@patch("scripts.l1_collect.fetcher._fetch_via_trafilatura")
@patch("scripts.l1_collect.fetcher._fetch_via_firecrawl")
def test_all_fail_returns_error(mock_fire, mock_traf, mock_bs):
    mock_fire.return_value = None
    mock_traf.return_value = None
    mock_bs.return_value = None
    r = fetch_article("https://x.gov.cn/a")
    assert r.via == "fetch_error"
    assert r.body is None
