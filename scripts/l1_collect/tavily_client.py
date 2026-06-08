"""Tavily 搜索 REST 客户端(urllib,无新依赖)。用于渠道发现:搜机构政策列表页。"""
from __future__ import annotations
import json
import os
from typing import Callable, Optional

TAVILY_URL = "https://api.tavily.com/search"


class TavilyClient:
    def __init__(self, api_key: Optional[str] = None, _post: Optional[Callable] = None):
        self.api_key = api_key if api_key is not None else os.environ.get("TAVILY_API_KEY")
        self._post = _post or self._http_post

    def search_urls(self, query: str, max_results: int = 5) -> list:
        if not self.api_key:
            return []
        try:
            data = self._post(TAVILY_URL, {
                "query": query, "max_results": max_results,
                "search_depth": "basic",
            }, self.api_key)
        except Exception:
            return []
        return [r["url"] for r in (data.get("results") or []) if r.get("url")]

    @staticmethod
    def _http_post(url: str, payload: dict, api_key: str) -> dict:
        import urllib.request
        body = json.dumps({**payload, "api_key": api_key}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
