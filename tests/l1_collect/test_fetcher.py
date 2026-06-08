"""Tests for fetcher (all external calls mocked)."""
from __future__ import annotations
import importlib
import pytest
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


class _Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._d = data
    def json(self):
        return self._d


def test_firecrawl_hits_v1_and_respects_min_len(monkeypatch):
    calls = []
    def fake_post(url, **kw):
        calls.append(url)
        return _Resp(200, {"data": {"markdown": "x" * 600}})
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.setattr("requests.post", fake_post)
    import scripts.l1_collect.fetcher as m
    importlib.reload(m)
    out = m._fetch_via_firecrawl("https://x.gov.cn/a")
    assert calls and "v1/scrape" in calls[0]
    assert out is not None and len(out) >= 500


def test_firecrawl_rejects_short(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.setattr("requests.post",
                        lambda url, **kw: _Resp(200, {"data": {"markdown": "x" * 300}}))
    import scripts.l1_collect.fetcher as m
    importlib.reload(m)
    assert m._fetch_via_firecrawl("https://x.gov.cn/a") is None
