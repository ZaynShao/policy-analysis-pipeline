from scripts.l1_collect.channel_catalog import Channel, ChannelStatus


def _ch():
    return Channel(city="广东省", province="广东省", level="省", city_code="440000",
                   channel_type="发改委", root_domain="drc.gd.gov.cn",
                   list_url="https://drc.gd.gov.cn/zcwj/", source="discovery",
                   status=ChannelStatus.验证)


def test_keywords_include_recall_gap_words():
    from scripts.l1_collect.step2_scan import KEYWORDS
    for w in ("换电", "现货市场", "绿证", "绿电", "车网互动", "V2G",
              "配电网", "加氢", "抽水蓄能", "需求侧"):
        assert w in KEYWORDS, f"漏词: {w}"


def test_extract_list_items_filters_by_keyword():
    from scripts.l1_collect.step2_scan import _extract_list_items
    html = '''<ul>
      <li><a href="/a.html">关于做好充电基础设施建设的通知</a> 2025-03-01</li>
      <li><a href="/b.html">关于食堂卫生检查的通知</a> 2025-03-02</li>
    </ul>'''
    rows = _extract_list_items(html, "https://drc.gd.gov.cn/zcwj/", _ch())
    titles = [r.title for r in rows]
    assert any("充电" in t for t in titles)
    assert all("食堂" not in t for t in titles)


def test_fetch_list_html_falls_back_to_firecrawl(monkeypatch):
    """BS4 拿空壳 → firecrawl 兜底被调用。"""
    from scripts.l1_collect import step2_scan as s
    monkeypatch.setattr(s, "_bs4_get",
                        lambda url: "<html><body></body></html>")  # 空壳
    called = {}

    def _fake_fc(url):
        called["fc"] = url
        return "<a href='/x'>充电通知</a>"

    monkeypatch.setattr(s, "_firecrawl_get_html", _fake_fc)
    html = s._fetch_list_html("https://x.gov.cn/list/")
    assert called.get("fc") == "https://x.gov.cn/list/"
    assert "充电" in html


def test_fetch_list_html_keeps_bs4_when_rich(monkeypatch):
    """BS4 内容够 → 不调 firecrawl。"""
    from scripts.l1_collect import step2_scan as s
    rich = "<a href='/x'>充电通知</a>" * 200   # 800 chars 文本 > LIST_MIN_TEXT(500)
    monkeypatch.setattr(s, "_bs4_get", lambda url: rich)
    monkeypatch.setattr(s, "_firecrawl_get_html",
                        lambda url: (_ for _ in ()).throw(AssertionError("不该调firecrawl")))
    html = s._fetch_list_html("https://x.gov.cn/list/")
    assert "充电" in html


def test_paginate_urls_uses_index_n_pattern():
    from scripts.l1_collect.step2_scan import _page_urls
    urls = _page_urls("https://x.gov.cn/zcwj/index.html", max_pages=3)
    assert "https://x.gov.cn/zcwj/index.html" in urls
    assert any("index_1" in u or "index_2" in u for u in urls)


def test_bs4_get_fixes_mojibake_encoding(monkeypatch):
    """政府站谎报 charset(ISO-8859-1) → _bs4_get 用 apparent_encoding 纠正中文乱码。"""
    from scripts.l1_collect import step2_scan as s

    class _FakeResp:
        def __init__(self):
            self.status_code = 200
            self.encoding = "ISO-8859-1"      # 头里的(错的)
            self.apparent_encoding = "utf-8"  # chardet 探测(对的)

        @property
        def text(self):
            return "关于印发新能源通知" if self.encoding == "utf-8" else "å³äºæ°"

    monkeypatch.setattr(s.requests, "get", lambda *a, **k: _FakeResp())
    out = s._bs4_get("https://www.ndrc.gov.cn/xwdt/tzgg")
    assert "新能源" in out  # 已按 apparent_encoding 解码,非乱码
