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
