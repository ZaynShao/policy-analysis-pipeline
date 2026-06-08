def test_search_returns_urls_via_injected_post():
    from scripts.l1_collect.tavily_client import TavilyClient
    captured = {}
    def fake_post(url, payload, api_key):
        captured["url"] = url
        captured["q"] = payload["query"]
        return {"results": [
            {"url": "https://ndrc.gov.cn/zcfb/", "title": "政策发布", "content": "..."},
            {"url": "https://ndrc.gov.cn/news/", "title": "新闻", "content": "..."},
        ]}
    c = TavilyClient(api_key="tvly-test", _post=fake_post)
    urls = c.search_urls("国家发改委 政策文件 列表", max_results=2)
    assert "https://ndrc.gov.cn/zcfb/" in urls
    assert captured["url"].endswith("/search")
    assert "发改委" in captured["q"]


def test_search_empty_on_no_key():
    from scripts.l1_collect.tavily_client import TavilyClient
    c = TavilyClient(api_key=None)
    assert c.search_urls("anything") == []
