"""代理兜底路径测试(Task 4:fetcher 代理运行时兜底)。"""
import os

from scripts.l1_collect import fetcher


def test_no_proxy_env_means_pure_direct_unchanged(monkeypatch):
    monkeypatch.delenv("POLICY_FETCH_PROXY_URL", raising=False)
    monkeypatch.setattr(fetcher, "_fetch_via_firecrawl", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_trafilatura", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_bs4", lambda url: None)
    r = fetcher.fetch_article("https://example.gov.cn/a")
    assert r.via == "fetch_error" and r.body is None


def test_proxy_retry_after_direct_exhausted(monkeypatch):
    monkeypatch.setenv("POLICY_FETCH_PROXY_URL", "http://proxy:1")
    monkeypatch.setattr(fetcher, "_fetch_via_firecrawl", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_trafilatura", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_bs4", lambda url: None)
    seen = {}

    def fake_proxy_fetch(url, proxy_url, extractor):
        seen["proxy"] = proxy_url
        return "正文" * 300

    monkeypatch.setattr(fetcher, "_fetch_via_proxy", fake_proxy_fetch)
    r = fetcher.fetch_article("https://example.gov.cn/a")
    assert r.via == "trafilatura+proxy"
    assert seen["proxy"] == "http://proxy:1"
    assert len(r.body) >= fetcher.MIN_BODY_LEN


def test_direct_success_never_touches_proxy(monkeypatch):
    monkeypatch.setenv("POLICY_FETCH_PROXY_URL", "http://proxy:1")
    monkeypatch.setattr(fetcher, "_fetch_via_firecrawl", lambda url: "正文" * 300)
    called = []
    monkeypatch.setattr(fetcher, "_fetch_via_proxy",
                        lambda *a, **k: called.append(1))
    r = fetcher.fetch_article("https://example.gov.cn/a")
    assert r.via == "firecrawl" and not called


class _FakeResp:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code


def test_fetch_via_proxy_passes_explicit_proxies_and_decodes_gbk(monkeypatch):
    seen = {}
    body = ("中文测试正文。" * 200)
    gbk_html = ("<html><head><meta charset=\"gbk\"></head><body><p>"
                + body + "</p></body></html>").encode("gbk")

    def fake_get(url, headers=None, timeout=None, proxies=None):
        seen["proxies"] = proxies
        return _FakeResp(gbk_html)

    monkeypatch.setattr(fetcher.requests, "get", fake_get)
    text = fetcher._fetch_via_proxy("https://example.gov.cn/a", "http://proxy:1",
                                    fetcher._extract_bs4)
    assert seen["proxies"] == {"http": "http://proxy:1", "https": "http://proxy:1"}
    assert text and "中文测试正文" in text   # 不是 mojibake


def test_fetch_via_proxy_rejects_http_error(monkeypatch):
    monkeypatch.setattr(fetcher.requests, "get",
                        lambda *a, **k: _FakeResp(b"x", status_code=403))
    assert fetcher._fetch_via_proxy("https://e.gov.cn/a", "http://proxy:1",
                                    fetcher._extract_bs4) is None


def test_proxy_path_does_not_mutate_environ(monkeypatch):
    # 纪律:fetcher 不得向 os.environ 写入 HTTP(S)_PROXY
    # 用 monkeypatch 先清除,再验证 fetcher 没有重写
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.setenv("POLICY_FETCH_PROXY_URL", "http://proxy:1")
    monkeypatch.setattr(fetcher, "_fetch_via_firecrawl", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_trafilatura", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_bs4", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_proxy", lambda *a: None)
    fetcher.fetch_article("https://example.gov.cn/a")
    assert "HTTP_PROXY" not in os.environ and "HTTPS_PROXY" not in os.environ
