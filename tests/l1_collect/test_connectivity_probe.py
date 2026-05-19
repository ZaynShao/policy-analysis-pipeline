"""Tests for connectivity_probe."""
from __future__ import annotations
from unittest.mock import patch, MagicMock

from scripts.l1_collect.connectivity_probe import (
    probe_url, looks_like_list_page,
)


def test_looks_like_list_page_positive():
    """含 a 标签 + 邻近日期 ≥3 = 列表页。"""
    html = """<html><body>
    <ul>
      <li><a href="/art/2025/5/1/art_001.html">关于xx的通知</a> 2025-05-01</li>
      <li><a href="/art/2025/5/2/art_002.html">关于yy的办法</a> 2025-05-02</li>
      <li><a href="/art/2025/5/3/art_003.html">关于zz的意见</a> 2025-05-03</li>
    </ul>
    <div class="page">1 2 3 下一页</div>
    </body></html>"""
    assert looks_like_list_page(html) is True


def test_looks_like_list_page_negative():
    """单条详情页或纯导航。"""
    html = "<html><body><h1>404 Not Found</h1></body></html>"
    assert looks_like_list_page(html) is False


@patch("scripts.l1_collect.connectivity_probe.requests.get")
def test_probe_url_ok(mock_get):
    mock_resp = MagicMock(status_code=200, text="""
    <ul><li><a href="/art/1.html">通知1</a> 2025-01-01</li>
        <li><a href="/art/2.html">通知2</a> 2025-01-02</li>
        <li><a href="/art/3.html">通知3</a> 2025-01-03</li></ul>
    <div class="pagination">下一页</div>
    """)
    mock_get.return_value = mock_resp
    result = probe_url("https://fgw.hangzhou.gov.cn/col/x/index.html")
    assert result.verdict == "ok"
    assert result.http_status == 200
    assert result.page_has_list_pattern is True


@patch("scripts.l1_collect.connectivity_probe.requests.get")
def test_probe_url_http_error(mock_get):
    mock_get.side_effect = Exception("ConnectionError")
    result = probe_url("https://nonexistent.gov.cn/x")
    assert result.verdict == "http_error"
