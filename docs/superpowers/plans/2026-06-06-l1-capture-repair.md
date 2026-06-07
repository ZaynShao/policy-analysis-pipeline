# L1 采集修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 L1 采集层升级为「全面（国家+省31+重点48）+ 质量门控 + 可定期审计」，填上决策层需要的全国态势。

**Architecture:** 分层兜底采集（BS4 免费先试 → firecrawl 渲染兜底）；Tavily+LLM 渠道发现治写死 URL 烂；L2 模式质量门（heuristic→LLM judge + golden 校准 planted-recall≥0.9）；重抓单调只增护栏；纯函数 `run_incremental` 作 service 线调用入口。

**Tech Stack:** Python 3.9, requests, BeautifulSoup4, trafilatura, pdfplumber, firecrawl v1, Tavily REST(urllib), `OpenAICompatClient`(deepseek-v4-flash), pytest, yaml

**Spec:** `docs/superpowers/specs/2026-06-06-l1-capture-repair-design.md`
**Worktree:** `~/dev/政策分析-pipeline-l1-repair` (branch `feat/l1-capture-repair` off main `ab2d542`)
**Env:** `set -a; . ~/.config/policy-pipeline/models.env; set +a`（含 FIRECRAWL_API_KEY / TAVILY_API_KEY / DEEPSEEK_API_KEY，out-of-git）

## 验收标准分两层（贯穿全 plan）
- **A 类·纯逻辑**：确定性 pytest，红→绿。网络调用在单测里 mock，测"给定响应逻辑对不对"。
- **B 类·网络/集成**：钉一个可观测阈值断言（如 planted-recall≥0.9 / 验证渠道数≥8 / 江苏充电 0→>0 / 无 raw 缩短）。
- **红线**：没有任何一步"完成"=「跑了一下」而不带可观测断言。

## 文件结构
```
scripts/l1_collect/
  fetcher.py            改  firecrawl v0→v1, MIN_BODY_LEN 200→500
  tavily_client.py      新  Tavily REST 搜索(urllib,无新依赖)
  channel_discovery.py  新  目标表+LLM选列表页URL+probe验证+幂等append
  step2_scan.py         改  分层兜底(BS4→firecrawl)+真翻页+拓关键词
  policy_gate.py        新  heuristic→LLM judge, GateResult/GoldenRecord, gate_corpus
  pdf_refetch.py        新  should_refetch谓词 + 单调只增护栏 + upgrade
  common_llm_client.py  新  从env构建judge client(无env返None)
  run_incremental.py    新  方法本体 run(config)→summary, level过滤, 软锁, gate接线
  audit_coverage.py     新  省×主题矩阵+零覆盖+新鲜度+缺口归因+HTML
tests/l1_collect/
  test_fetcher.py(改) test_tavily_client.py test_channel_discovery.py
  test_step2_scan.py(改) test_policy_gate.py test_pdf_refetch.py
  test_run_incremental.py test_audit_coverage.py
scripts/_oneshot/
  build_l1_golden.py            一次性:抽样+造planted
  expand_channels_2026-06-06.py 一次性:发现+写catalog
  run_pdf_refetch_2026-06-06.py 一次性:重抓薄政策
```

---

## Task 1: fetcher.py — firecrawl v1 升级

**Files:**
- Modify: `scripts/l1_collect/fetcher.py`
- Test: `tests/l1_collect/test_fetcher.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/l1_collect/test_fetcher.py（新建）
import importlib
import pytest


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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ~/dev/政策分析-pipeline-l1-repair && python -m pytest tests/l1_collect/test_fetcher.py -v`
Expected: FAIL（现 v0 端点 + MIN_BODY_LEN=200）

- [ ] **Step 3: 改 fetcher.py**

改两处：
```python
MIN_BODY_LEN = 500  # 旧 200
```
```python
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",  # 旧 v0/scrape
            json={"url": url, "formats": ["markdown"]},
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
        )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_collect/test_fetcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/fetcher.py tests/l1_collect/test_fetcher.py
git commit -m "feat(l1): firecrawl v0→v1 + MIN_BODY_LEN 200→500"
```

---

## Task 2: tavily_client.py — Tavily REST 搜索

**Files:**
- Create: `scripts/l1_collect/tavily_client.py`
- Test: `tests/l1_collect/test_tavily_client.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/l1_collect/test_tavily_client.py
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_collect/test_tavily_client.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现 tavily_client.py**

```python
# scripts/l1_collect/tavily_client.py
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_collect/test_tavily_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/tavily_client.py tests/l1_collect/test_tavily_client.py
git commit -m "feat(l1): Tavily REST 搜索客户端(urllib,无新依赖)"
```

---

## Task 3: channel_discovery.py — 渠道发现

**Files:**
- Create: `scripts/l1_collect/channel_discovery.py`
- Test: `tests/l1_collect/test_channel_discovery.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/l1_collect/test_channel_discovery.py
import json


def test_national_targets_cover_three_lines():
    from scripts.l1_collect.channel_discovery import NATIONAL_TARGETS
    domains = {t["root_domain"] for t in NATIONAL_TARGETS}
    assert {"ndrc.gov.cn", "nea.gov.cn", "miit.gov.cn", "www.gov.cn"} <= domains
    assert len(NATIONAL_TARGETS) >= 13


def test_province_targets_from_registry():
    from scripts.l1_collect.channel_discovery import province_targets_from_registry
    from pathlib import Path
    reg = Path.home() / "Documents/Zayn Main/政策分析/_meta/channel_registry.yaml"
    targets = province_targets_from_registry(reg)
    provs = {t["province"] for t in targets}
    for p in ("广东省", "江苏省", "浙江省", "四川省", "山东省"):
        assert p in provs


def test_pick_list_url_parses_llm_json():
    from scripts.l1_collect.channel_discovery import pick_list_url
    def fake_llm(system, user, max_tokens=512):
        return json.dumps({"list_url": "https://ndrc.gov.cn/zcfb/",
                           "confidence": 0.9, "reason": "政策发布栏目"})
    url = pick_list_url(
        target_name="国家发展和改革委员会",
        candidate_urls=["https://ndrc.gov.cn/zcfb/", "https://ndrc.gov.cn/news/"],
        llm_fn=fake_llm,
    )
    assert url == "https://ndrc.gov.cn/zcfb/"


def test_pick_list_url_none_when_no_candidates():
    from scripts.l1_collect.channel_discovery import pick_list_url
    assert pick_list_url("x", [], llm_fn=lambda s, u, **k: "{}") is None


def test_discover_builds_verified_channel(monkeypatch):
    """Tavily 给候选 → LLM 选 → probe ok → status=验证。"""
    from scripts.l1_collect import channel_discovery as cd
    from scripts.l1_collect.connectivity_probe import ProbeResult
    monkeypatch.setattr(cd, "_tavily_search",
                        lambda q: ["https://ndrc.gov.cn/zcfb/"])
    monkeypatch.setattr(cd, "_llm_pick",
                        lambda name, urls: "https://ndrc.gov.cn/zcfb/")
    monkeypatch.setattr(cd, "probe_url",
                        lambda u: ProbeResult(url=u, http_status=200,
                                              page_has_list_pattern=True, verdict="ok"))
    ch = cd.discover_one({
        "city": "国家发展和改革委员会", "province": "国家", "level": "国家",
        "city_code": "000000", "channel_type": "发改委",
        "root_domain": "ndrc.gov.cn",
    })
    assert ch is not None
    assert ch.list_url == "https://ndrc.gov.cn/zcfb/"
    assert ch.status.value == "验证"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_collect/test_channel_discovery.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现 channel_discovery.py**

```python
# scripts/l1_collect/channel_discovery.py
"""渠道发现:决策A目标 → Tavily搜 → LLM选真列表页URL → probe验证 → Channel。

治根因:写死URL当天烂(实测国务院403/能源局404)。LLM管"哪个URL是政策列表页"的判断。
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Callable, Optional
import yaml

from .channel_catalog import Channel, ChannelStatus
from .connectivity_probe import probe_url
from .tavily_client import TavilyClient

# 决策A:国家级13核心机构(覆盖加油/充电/电力三业务线)
NATIONAL_TARGETS = [
    {"city": "国家发展和改革委员会", "channel_type": "发改委", "root_domain": "ndrc.gov.cn"},
    {"city": "国家能源局", "channel_type": "能源局", "root_domain": "nea.gov.cn"},
    {"city": "工业和信息化部", "channel_type": "工信部", "root_domain": "miit.gov.cn"},
    {"city": "商务部", "channel_type": "商务部", "root_domain": "mofcom.gov.cn"},
    {"city": "国务院", "channel_type": "国务院", "root_domain": "www.gov.cn"},
    {"city": "财政部", "channel_type": "财政部", "root_domain": "mof.gov.cn"},
    {"city": "住房和城乡建设部", "channel_type": "住建部", "root_domain": "mohurd.gov.cn"},
    {"city": "国家市场监督管理总局", "channel_type": "市监总局", "root_domain": "samr.gov.cn"},
    {"city": "交通运输部", "channel_type": "交通运输部", "root_domain": "mot.gov.cn"},
    {"city": "生态环境部", "channel_type": "生态环境部", "root_domain": "mee.gov.cn"},
    {"city": "国家标准化管理委员会", "channel_type": "标准委", "root_domain": "sac.gov.cn"},
    {"city": "中国人民银行", "channel_type": "央行", "root_domain": "pbc.gov.cn"},
    {"city": "国家税务总局", "channel_type": "税务总局", "root_domain": "chinatax.gov.cn"},
]

for _t in NATIONAL_TARGETS:
    _t.update({"province": "国家", "level": "国家", "city_code": "000000"})

_PROV_CODE = {
    "北京市": "11", "天津市": "12", "河北省": "13", "山西省": "14", "内蒙古自治区": "15",
    "辽宁省": "21", "吉林省": "22", "黑龙江省": "23", "上海市": "31", "江苏省": "32",
    "浙江省": "33", "安徽省": "34", "福建省": "35", "江西省": "36", "山东省": "37",
    "河南省": "41", "湖北省": "42", "湖南省": "43", "广东省": "44", "广西壮族自治区": "45",
    "海南省": "46", "重庆市": "50", "四川省": "51", "贵州省": "52", "云南省": "53",
    "西藏自治区": "54", "陕西省": "61", "甘肃省": "62", "青海省": "63",
    "宁夏回族自治区": "64", "新疆维吾尔自治区": "65",
}

_SYSTEM_PICK = (
    "你在为政策采集系统挑选『政策文件列表页』URL。从候选里选出最像"
    "「持续更新的政策/通知/公告列表栏目」的那个(不是首页、不是单篇文章、不是检索结果页)。"
    '只输出 JSON:{"list_url":"<选中url或空>","confidence":0-1,"reason":"<=20字"}'
)


def province_targets_from_registry(registry_path: Path) -> list:
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or []
    out, seen = [], set()
    for e in raw:
        region = e.get("region") or {}
        if region.get("level") != "省":
            continue
        prov = region.get("name") or ""
        domain = e.get("domain") or ""
        if not prov or prov not in _PROV_CODE or domain in seen:
            continue
        seen.add(domain)
        issuer = e.get("issuer_canonical") or ""
        ctype = "发改委" if ("发展" in issuer or "改革" in issuer) else \
                "能源局" if "能源" in issuer else "政府网"
        out.append({
            "city": prov, "province": prov, "level": "省",
            "city_code": f"{_PROV_CODE[prov]}0000",
            "channel_type": ctype, "root_domain": domain,
        })
    return out


def _tavily_search(query: str) -> list:
    return TavilyClient().search_urls(query, max_results=5)


def _llm_pick(target_name: str, candidate_urls: list) -> Optional[str]:
    from .common_llm_client import make_judge_client
    llm = make_judge_client()
    if llm is None:
        return None
    return pick_list_url(target_name, candidate_urls, llm)


def pick_list_url(target_name: str, candidate_urls: list,
                  llm_fn: Callable) -> Optional[str]:
    if not candidate_urls:
        return None
    user = f"机构:{target_name}\n候选URL:\n" + "\n".join(candidate_urls)
    try:
        data = json.loads(llm_fn(_SYSTEM_PICK, user))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    url = (data.get("list_url") or "").strip()
    return url if url in candidate_urls else None


def discover_one(target: dict) -> Optional[Channel]:
    """单目标:搜→选→验证。verdict=ok→验证;否则候选(留firecrawl兜底)。"""
    query = f"{target['city']} 政策文件 通知公告 列表"
    candidates = _tavily_search(query)
    list_url = _llm_pick(target["city"], candidates)
    if not list_url:
        list_url = f"https://{target['root_domain']}/"  # 兜底首页
    pr = probe_url(list_url)
    status = ChannelStatus.验证 if pr.verdict == "ok" else ChannelStatus.候选
    return Channel(
        city=target["city"], province=target["province"], level=target["level"],
        city_code=target["city_code"], channel_type=target["channel_type"],
        root_domain=target["root_domain"], list_url=list_url,
        source="discovery", status=status,
        last_probed_at=pr.probed_at, probe_result=pr.verdict,
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_collect/test_channel_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/channel_discovery.py tests/l1_collect/test_channel_discovery.py
git commit -m "feat(l1): 渠道发现(目标表+Tavily搜+LLM选列表页+probe验证)"
```

---

## Task 4: step2_scan.py — 分层兜底扫描

**背景:** 现状纯 BS4（JS/反爬页拿空）+ `?page=N` 翻页假设错 + KEYWORDS 漏词。改为分层兜底 + 真翻页 + 拓词。

**Files:**
- Modify: `scripts/l1_collect/step2_scan.py`
- Test: `tests/l1_collect/test_step2_scan.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/l1_collect/test_step2_scan.py
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
    monkeypatch.setattr(s, "_firecrawl_get_html",
                        lambda url: called.setdefault("fc", url) or "<a href='/x'>充电通知</a>")
    html = s._fetch_list_html("https://x.gov.cn/list/")
    assert called.get("fc") == "https://x.gov.cn/list/"
    assert "充电" in html


def test_fetch_list_html_keeps_bs4_when_rich(monkeypatch):
    """BS4 内容够 → 不调 firecrawl。"""
    from scripts.l1_collect import step2_scan as s
    rich = "<a href='/x'>充电通知</a>" * 50
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_collect/test_step2_scan.py -v`
Expected: FAIL（KEYWORDS 缺词 + `_fetch_list_html`/`_page_urls`/`_bs4_get`/`_firecrawl_get_html` 不存在）

- [ ] **Step 3: 改 step2_scan.py**

3a — 拓 KEYWORDS（在现有元组末尾追加）：
```python
KEYWORDS = (
    "能源", "电力", "电网", "油气", "成品油", "充电", "储能",
    "新能源", "双碳", "光伏", "风电", "氢能", "天然气", "汽车以旧换新",
    "新型电力", "虚拟电厂", "需求响应", "碳达峰", "碳中和",
    # 召回偏向补漏(L1体检暴露的盲词)
    "换电", "现货市场", "绿证", "绿电", "车网互动", "V2G",
    "配电网", "分布式", "加氢", "抽水蓄能", "需求侧", "电价",
)
```

3b — 新增分层抓取 + 翻页函数（放在 `_extract_list_items` 上方）：
```python
LIST_MIN_TEXT = 500   # BS4 文本短于此视为空壳/JS页 → firecrawl 兜底


def _bs4_get(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code >= 400:
            return ""
        return r.text or ""
    except Exception:
        return ""


def _firecrawl_get_html(url: str) -> str:
    import os
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return ""
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            json={"url": url, "formats": ["html"]},
            headers={"Authorization": f"Bearer {key}"}, timeout=45,
        )
        if resp.status_code != 200:
            return ""
        d = resp.json().get("data") or {}
        return d.get("html") or d.get("rawHtml") or ""
    except Exception:
        return ""


def _fetch_list_html(url: str) -> str:
    """分层:BS4免费先试;空壳/反爬 → firecrawl渲染兜底。"""
    html = _bs4_get(url)
    soup = BeautifulSoup(html, "html.parser") if html else None
    text_len = len(soup.get_text(strip=True)) if soup else 0
    if text_len >= LIST_MIN_TEXT:
        return html
    fc = _firecrawl_get_html(url)
    return fc or html


def _page_urls(list_url: str, max_pages: int = MAX_PAGES) -> list:
    """政府站常见翻页:index.html / index_1.html / index_2.html ... + ?page= 兜底。"""
    urls = [list_url]
    if list_url.endswith("index.html"):
        base = list_url[: -len("index.html")]
        for n in range(1, max_pages):
            urls.append(f"{base}index_{n}.html")
    else:
        for n in range(2, max_pages + 1):
            sep = "&" if "?" in list_url else "?"
            urls.append(f"{list_url}{sep}page={n}")
    return urls
```

3c — 改 `scan_channel` 用上面两函数（替换原翻页循环体内的 `requests.get`）：
```python
def scan_channel(ch: Channel, out_dir: Path) -> int:
    if ch.status != ChannelStatus.验证:
        return 0
    all_rows: list[ScanRow] = []
    seen_urls: set = set()
    for page_url in _page_urls(ch.list_url):
        html = _fetch_list_html(page_url)
        if not html:
            break
        rows = _extract_list_items(html, page_url, ch)
        new_rows = [x for x in rows if x.url not in seen_urls]
        for x in new_rows:
            seen_urls.add(x.url)
        all_rows.extend(new_rows)
        if rows and (len(new_rows) / max(1, len(rows))) < NEW_RATIO_THRESHOLD:
            break

    out_dir.mkdir(parents=True, exist_ok=True)
    fn = out_dir / f"{ch.city}__{ch.channel_type}__{ch.root_domain}.jsonl"
    fn.write_text(
        "\n".join(json.dumps(asdict(x), ensure_ascii=False) for x in all_rows),
        encoding="utf-8",
    )
    return len(all_rows)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_collect/test_step2_scan.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/step2_scan.py tests/l1_collect/test_step2_scan.py
git commit -m "feat(l1): scan分层兜底(BS4→firecrawl)+真翻页(index_N)+拓关键词"
```

---

## Task 5: policy_gate.py — 采集质量门

**Files:**
- Create: `scripts/l1_collect/policy_gate.py`
- Test: `tests/l1_collect/test_policy_gate.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/l1_collect/test_policy_gate.py
import json


def test_obvious_policy_skips_llm():
    from scripts.l1_collect.policy_gate import gate_one
    called = []
    r = gate_one(ref="r1",
                 url="https://ndrc.gov.cn/xxgk/zcfb/202501/d.html",
                 title="关于推进充电基础设施建设的指导意见",
                 body_head="根据国务院部署,现就有关事项通知如下:",
                 llm_fn=lambda s, u, **k: called.append(1) or "{}")
    assert r.label == "policy" and r.used_llm is False and r.action == "pass"
    assert not called


def test_blacklist_fast_reject():
    from scripts.l1_collect.policy_gate import gate_one
    r = gate_one(ref="r2", url="https://in-en.com/a.html",
                 title="充电桩市场快速增长", body_head="据记者了解...",
                 llm_fn=lambda s, u, **k: "{}")
    assert r.action == "reject" and r.used_llm is False


def test_borderline_calls_llm():
    from scripts.l1_collect.policy_gate import gate_one
    called = []
    def llm(s, u, max_tokens=512):
        called.append(1)
        return json.dumps({"label": "non_policy_index", "confidence": 0.85,
                          "evidence": "仅列表链接"})
    r = gate_one(ref="r3", url="https://fgw.gd.gov.cn/index.html",
                 title="政策文件目录", body_head="2025-01 政策A\n2024-12 政策B",
                 llm_fn=llm)
    assert called and r.used_llm is True and r.action == "reject"


def test_low_conf_to_review_queue():
    from scripts.l1_collect.policy_gate import gate_one
    r = gate_one(ref="r4", url="https://fgw.hunan.gov.cn/x.html",
                 title="关于某事项的通知", body_head="现就若干事项告知...",
                 llm_fn=lambda s, u, **k: json.dumps(
                     {"label": "non_policy_news", "confidence": 0.55, "evidence": "x"}))
    assert r.action == "review_queue"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_collect/test_policy_gate.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现 policy_gate.py**

```python
# scripts/l1_collect/policy_gate.py
"""L1采集质量门:heuristic预筛→LLM judge。复用 news_filter 规则,搬到采集时inline。
明显政策直通/明显非政策快拒/灰区LLM打标。低置信→review_queue(不静默丢)。"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
from typing import Callable, Optional

from .news_filter import is_news_or_press, GOV_DOMAIN_SUFFIXES

REVIEW_THRESHOLD = 0.7
POLICY_TITLE_SIGNALS = ("通知", "意见", "规定", "办法", "方案", "决定", "公告",
                        "批复", "措施", "规划", "细则", "标准", "条例", "暂行", "导则")
BODY_POLICY_SIGNALS = ("根据", "现就", "现将", "特此通知", "有关规定", "现通知如下")
FAST_REJECT_DOMAINS = {
    "xinhuanet.com", "people.com.cn", "cctv.com", "thepaper.cn", "sohu.com",
    "sina.com.cn", "163.com", "qq.com", "ifeng.com", "escn.com.cn",
    "in-en.com", "bjx.com.cn",
}

_SYSTEM = (
    "你是政策文档分类器。判断文档是『正式政策公文』还是非政策。只输出JSON。"
    'Schema:{"label":"policy|non_policy_index|non_policy_news|non_policy_reply",'
    '"confidence":0.0-1.0,"evidence":"<=30字"}'
)


@dataclass
class GateResult:
    ref: str
    label: str
    confidence: float
    evidence: str
    used_llm: bool
    action: str          # pass | reject | review_queue

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GoldenRecord:
    pid: str
    url: str
    title: str
    body_head: str
    gold_label: str
    is_planted: bool
    notes: str = ""


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _blacklisted(url: str) -> bool:
    h = _host(url)
    return any(h == d or h.endswith("." + d) for d in FAST_REJECT_DOMAINS)


def _is_gov(url: str) -> bool:
    h = _host(url)
    return any(h.endswith(s) for s in GOV_DOMAIN_SUFFIXES)


def _heuristic(url: str, title: str, body_head: str) -> str:
    if _blacklisted(url):
        return "non_policy"
    if _is_gov(url) and (any(s in title for s in POLICY_TITLE_SIGNALS)
                         or any(s in body_head for s in BODY_POLICY_SIGNALS)):
        return "policy"
    fr = is_news_or_press(url=url, title=title, issuer=None)
    hard = [r for r in fr.reasons if r != "issuer_unknown_but_gov_domain"]
    return "non_policy" if hard else "gray"


def gate_one(ref: str, url: str, title: str, body_head: str,
             llm_fn: Optional[Callable]) -> GateResult:
    v = _heuristic(url, title, body_head)
    if v == "policy":
        return GateResult(ref, "policy", 0.95, "heuristic_pass", False, "pass")
    if v == "non_policy":
        return GateResult(ref, "non_policy_news", 0.95, "heuristic_reject", False, "reject")
    if llm_fn is None:
        return GateResult(ref, "policy", 0.5, "llm_missing_assume_pass", False, "pass")
    user = f"标题:{title}\nURL:{url}\n正文开头:{body_head[:800]}"
    try:
        data = json.loads(llm_fn(_SYSTEM, user))
    except (json.JSONDecodeError, TypeError, ValueError):
        return GateResult(ref, "policy", 0.4, "llm_parse_error", True, "review_queue")
    label = data.get("label", "policy")
    conf = float(data.get("confidence", 0.5))
    ev = data.get("evidence", "")
    if label == "policy":
        action = "pass"
    elif conf < REVIEW_THRESHOLD:
        action = "review_queue"
    else:
        action = "reject"
    return GateResult(ref, label, conf, ev, True, action)


def gate_corpus(records: list, llm_fn: Callable) -> list:
    return [gate_one(r.pid, r.url, r.title, r.body_head, llm_fn) for r in records]
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_collect/test_policy_gate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/policy_gate.py tests/l1_collect/test_policy_gate.py
git commit -m "feat(l1): 采集质量门(heuristic→LLM judge, GateResult, review_queue)"
```

---

## Task 6: pdf_refetch.py — 母文件重抓 + 单调护栏

**Files:**
- Create: `scripts/l1_collect/pdf_refetch.py`
- Test: `tests/l1_collect/test_pdf_refetch.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/l1_collect/test_pdf_refetch.py
def test_should_refetch_thin_only():
    from scripts.l1_collect.pdf_refetch import _body_chars, should_refetch_text
    short = "---\npid: x\nsource_url: u\n---\n\n封面"
    rich = "---\npid: x\nsource_url: u\n---\n\n" + "正文。" * 400
    assert should_refetch_text(short) is True
    assert should_refetch_text(rich) is False


def test_monotonic_guard_blocks_shorter(tmp_path):
    """新捕获不比旧长 → 不写,返回 skipped。"""
    from scripts.l1_collect.pdf_refetch import upgrade_policy_body
    p = tmp_path / "P_x.md"
    old_body = "原始较长正文" * 100
    p.write_text(f"---\npid: P_x\nsource_url: https://x.gov.cn/d.pdf\n---\n\n{old_body}",
                 encoding="utf-8")
    res = upgrade_policy_body(p, fetch_fn=lambda url: "短")  # 比旧短
    assert res["upgraded"] is False
    assert res["reason"] == "not_longer"
    assert old_body in p.read_text(encoding="utf-8")  # 原文未动


def test_upgrade_writes_when_strictly_longer(tmp_path):
    from scripts.l1_collect.pdf_refetch import upgrade_policy_body
    p = tmp_path / "P_y.md"
    p.write_text("---\npid: P_y\nsource_url: https://x.gov.cn/d.pdf\n---\n\n封面",
                 encoding="utf-8")
    new = "第一条 本办法适用于...。" * 80
    res = upgrade_policy_body(p, fetch_fn=lambda url: new)
    assert res["upgraded"] is True
    assert res["new_chars"] > res["old_chars"]
    content = p.read_text(encoding="utf-8")
    assert "第一条" in content
    assert "source_url: https://x.gov.cn/d.pdf" in content  # frontmatter 不动


def test_skip_when_no_source_url(tmp_path):
    from scripts.l1_collect.pdf_refetch import upgrade_policy_body
    p = tmp_path / "P_z.md"
    p.write_text("---\npid: P_z\n---\n\n封面", encoding="utf-8")
    res = upgrade_policy_body(p, fetch_fn=lambda url: "x" * 9999)
    assert res["upgraded"] is False and res["reason"] == "no_source_url"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_collect/test_pdf_refetch.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现 pdf_refetch.py**

```python
# scripts/l1_collect/pdf_refetch.py
"""母文件重抓:body被截断(只抓到封面)的政策,从同一source_url重抓补全。
护栏:单调只增(新严格更长+同源才写)、谓词候选(非pid清单)、幂等、记provenance。§C合规。"""
from __future__ import annotations
import os
import re
import requests
from pathlib import Path
from typing import Callable, Optional

THIN_THRESHOLD = 800
PDF_URL_RE = re.compile(r"\.pdf(\?|$)", re.I)
TIMEOUT = 60


def _body_chars(content: str) -> int:
    parts = content.split("---", 2)
    body = parts[2] if len(parts) >= 3 else content
    return len(body.strip())


def should_refetch_text(content: str) -> bool:
    return _body_chars(content) < THIN_THRESHOLD


def should_refetch(policy_path: Path) -> bool:
    return should_refetch_text(policy_path.read_text(encoding="utf-8"))


def _fetch_via_pdfplumber(url: str) -> Optional[str]:
    if not PDF_URL_RE.search(url):
        return None
    try:
        import pdfplumber, io
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code >= 400:
            return None
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        return text if len(text) >= 200 else None
    except Exception:
        return None


def _fetch_via_firecrawl(url: str) -> Optional[str]:
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            json={"url": url, "formats": ["markdown"]},
            headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        md = (resp.json().get("data") or {}).get("markdown") or ""
        return md if len(md) >= 200 else None
    except Exception:
        return None


def fetch_pdf_content(url: str) -> Optional[str]:
    return _fetch_via_pdfplumber(url) or _fetch_via_firecrawl(url)


def upgrade_policy_body(policy_path: Path,
                        fetch_fn: Callable[[str], Optional[str]] = fetch_pdf_content) -> dict:
    content = policy_path.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {"upgraded": False, "reason": "no_frontmatter"}
    front, body_old = parts[1], parts[2]
    m = re.search(r"^source_url:\s*(.+)$", front, re.M)
    if not m:
        return {"upgraded": False, "reason": "no_source_url"}
    url = m.group(1).strip()
    new_body = fetch_fn(url)
    if not new_body:
        return {"upgraded": False, "reason": "fetch_failed", "url": url}
    old_chars = len(body_old.strip())
    new_chars = len(new_body.strip())
    if new_chars <= old_chars:                       # 单调护栏:永不缩短/替换
        return {"upgraded": False, "reason": "not_longer",
                "old_chars": old_chars, "new_chars": new_chars}
    policy_path.write_text(f"---{front}---\n\n{new_body.strip()}\n", encoding="utf-8")
    return {"upgraded": True, "old_chars": old_chars, "new_chars": new_chars, "url": url}
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_collect/test_pdf_refetch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/pdf_refetch.py tests/l1_collect/test_pdf_refetch.py
git commit -m "feat(l1): 母文件重抓+单调只增护栏(同源严格更长才写raw)"
```

---

## Task 7: common_llm_client.py + run_incremental.py — 方法本体

**Files:**
- Create: `scripts/l1_collect/common_llm_client.py`
- Create: `scripts/l1_collect/run_incremental.py`
- Test: `tests/l1_collect/test_run_incremental.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/l1_collect/test_run_incremental.py
from scripts.l1_collect.channel_catalog import Channel, ChannelStatus


def _ch(level, domain):
    return Channel(city=("国家发改委" if level == "国家" else "广东省"),
                   province=("国家" if level == "国家" else "广东省"), level=level,
                   city_code="000000", channel_type="发改委", root_domain=domain,
                   list_url=f"https://{domain}/", source="discovery",
                   status=ChannelStatus.验证)


def test_select_channels_national_only():
    from scripts.l1_collect.run_incremental import _select_channels
    chans = [_ch("国家", "ndrc.gov.cn"), _ch("市", "gz.gov.cn")]
    out = _select_channels(chans, ["national"])
    assert len(out) == 1 and out[0].level == "国家"


def test_select_channels_province_city_excludes_national():
    from scripts.l1_collect.run_incremental import _select_channels
    chans = [_ch("国家", "ndrc.gov.cn"), _ch("省", "drc.gd.gov.cn"), _ch("市", "gz.gov.cn")]
    out = _select_channels(chans, ["province", "city"])
    assert all(c.level != "国家" for c in out) and len(out) == 2


def test_gate_extracted_routes_pass_and_reject(tmp_path):
    """gate=pass→进ingest桶;reject→进quarantine,不进ingest桶。"""
    import json
    from scripts.l1_collect.run_incremental import _gate_extracted_dir
    ext = tmp_path / "ext"; ext.mkdir()
    passed = tmp_path / "passed"; passed.mkdir()
    quar = tmp_path / "q.jsonl"
    (ext / "a.json").write_text(json.dumps({
        "url": "https://ndrc.gov.cn/zcfb/d.html",
        "title": "关于充电设施的通知", "body": "根据部署,现通知如下:" + "正文" * 50}),
        encoding="utf-8")
    (ext / "b.json").write_text(json.dumps({
        "url": "https://in-en.com/x.html", "title": "市场快讯", "body": "据记者"}),
        encoding="utf-8")
    n_pass, n_rej = _gate_extracted_dir(ext, passed, quar, llm_fn=None)
    assert n_pass == 1 and n_rej == 1
    assert (passed / "a.json").exists()
    assert not (passed / "b.json").exists()
    assert quar.exists() and "in-en" in quar.read_text()


def test_soft_lock_noop_when_service_absent():
    """service.l1_status 不在树上 → 软锁 no-op,不报错。"""
    from scripts.l1_collect.run_incremental import _l1_lock
    with _l1_lock():
        pass  # 不抛异常即通过
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_collect/test_run_incremental.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3a: 实现 common_llm_client.py**

```python
# scripts/l1_collect/common_llm_client.py
"""从 env 构建质量门 judge client(deepseek-flash)。无 env → None(逻辑层 fallback)。"""
from __future__ import annotations
import os
from typing import Callable, Optional


def make_judge_client() -> Optional[Callable]:
    base = os.environ.get("OPENAI_BASE_URL")
    key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("JUDGE_MODEL", "deepseek-v4-flash")
    if not (base and key):
        return None
    from scripts.common.llm import OpenAICompatClient
    return OpenAICompatClient(model=model, log_path="state/l1_gate/gate_calls.jsonl",
                              base_url=base, api_key=key).complete
```

- [ ] **Step 3b: 实现 run_incremental.py**

```python
# scripts/l1_collect/run_incremental.py
"""L1增量采集入口。service线调用,无调度逻辑。append-only。
流程:取锁→Step2分层扫→Step3规则过滤→Step4抓→Step4.5抽→policy_gate门→Step5入库→释放锁。
"""
from __future__ import annotations
import argparse
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .channel_catalog import load_catalog, ChannelStatus
from .step2_scan import scan_channel
from .step3_filter import filter_scan_rows
from .step4_fetch import fetch_candidates
from .step4_5_extract import extract_all
from .step5_ingest import ingest_extracted
from .dedup import DedupIndex
from .policy_gate import gate_one
from .common_llm_client import make_judge_client

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
VAULT_POLICIES = Path.home() / "Documents" / "Zayn Main" / "政策分析" / "0_raw" / "policies"
LEVEL_MAP = {"national": "国家", "province": "省", "city": "市"}


@dataclass
class IncrementalConfig:
    level: list = field(default_factory=lambda: ["national", "province", "city"])
    since: str = "2026-01-01"
    dry_run: bool = False
    state_dir: Path = STATE / "T1_incremental"
    vault_dir: Path = VAULT_POLICIES


@contextmanager
def _l1_lock():
    """复用 service 的 l1_status 锁(若在树上);不在 → no-op(边界:不重复造锁)。"""
    try:
        from scripts.service.l1_status import acquire  # type: ignore
    except Exception:
        acquire = None
    if acquire is None:
        yield
        return
    with acquire():
        yield


def _select_channels(channels, levels: list):
    cn = {LEVEL_MAP.get(l, l) for l in levels}
    return [c for c in channels if c.level in cn and c.status == ChannelStatus.验证]


def _gate_extracted_dir(ext_dir: Path, passed_dir: Path,
                        quar_jsonl: Path, llm_fn) -> tuple:
    passed_dir.mkdir(parents=True, exist_ok=True)
    n_pass = n_rej = 0
    rejects: list = []
    for jf in sorted(ext_dir.glob("*.json")):
        rec = json.loads(jf.read_text(encoding="utf-8"))
        gr = gate_one(ref=jf.stem, url=rec.get("url", ""), title=rec.get("title", ""),
                      body_head=(rec.get("body") or "")[:800], llm_fn=llm_fn)
        if gr.action == "pass":
            (passed_dir / jf.name).write_text(jf.read_text(encoding="utf-8"),
                                              encoding="utf-8")
            n_pass += 1
        else:
            rejects.append({"file": jf.name, **gr.to_dict()})
            n_rej += 1
    if rejects:
        quar_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(quar_jsonl, "a", encoding="utf-8") as f:
            for r in rejects:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return n_pass, n_rej


def _run_channel(ch, cfg: IncrementalConfig, dedup, llm_fn) -> dict:
    sd = cfg.state_dir
    for d in ["scan", "cand", "quar", "fetch", "ext", "passed", "ingest"]:
        (sd / d).mkdir(parents=True, exist_ok=True)
    label = f"{ch.city}__{ch.channel_type}__{ch.root_domain}"
    n_scan = scan_channel(ch, sd / "scan")
    if n_scan == 0:
        return {"channel": label, "scanned": 0, "ingested": 0}
    merged = sd / "scan" / f"_merged_{ch.root_domain}.jsonl"
    src = sd / "scan" / f"{label}.jsonl"
    merged.write_text(src.read_text(encoding="utf-8") if src.exists() else "",
                      encoding="utf-8")
    cand = sd / "cand" / f"{label}.jsonl"
    kept, _ = filter_scan_rows(merged, cand, sd / "quar" / f"{label}__s3.jsonl", dedup)
    if cfg.dry_run:
        return {"channel": label, "scanned": n_scan, "kept": kept, "ingested": 0}
    fetch_candidates(cand, sd / "fetch", sd / "quar" / f"{label}__ferr.txt")
    extract_all(sd / "fetch", sd / "ext", sd / "quar" / f"{label}__s45.jsonl")
    n_pass, n_rej = _gate_extracted_dir(sd / "ext", sd / "passed",
                                        sd / "quar" / "gate_rejects.jsonl", llm_fn)
    ing_ok, _ = ingest_extracted(sd / "passed", sd / "ingest" / f"{label}.jsonl")
    # 清空 ext/passed 供下个渠道复用(避免跨渠道串)
    for d in ["fetch", "ext", "passed"]:
        for f in (sd / d).glob("*.json"):
            f.unlink()
    return {"channel": label, "scanned": n_scan, "kept": kept,
            "gate_passed": n_pass, "gate_rejected": n_rej, "ingested": ing_ok}


def run_incremental(cfg: IncrementalConfig) -> dict:
    catalog = load_catalog(ROOT / "state/T1_channels/channel_catalog.yaml")
    channels = _select_channels(catalog, cfg.level)
    print(f"[run_incremental] level={cfg.level} channels={len(channels)} dry={cfg.dry_run}")
    llm_fn = None if cfg.dry_run else make_judge_client()
    results = []
    with _l1_lock():
        dedup = DedupIndex.from_vault_policies(cfg.vault_dir)
        for ch in channels:
            r = _run_channel(ch, cfg, dedup, llm_fn)
            results.append(r)
            print(f"  {r['channel'][:48]:48s} scan={r['scanned']} ing={r.get('ingested',0)}")
    summary = {
        "channels_run": len(results),
        "total_scanned": sum(r["scanned"] for r in results),
        "total_ingested": sum(r.get("ingested", 0) for r in results),
        "total_gate_rejected": sum(r.get("gate_rejected", 0) for r in results),
        "dry_run": cfg.dry_run,
    }
    print(f"[run_incremental] DONE {summary}")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="national,province,city")
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    run_incremental(IncrementalConfig(level=a.level.split(","), since=a.since,
                                      dry_run=a.dry_run))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_collect/test_run_incremental.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/common_llm_client.py scripts/l1_collect/run_incremental.py \
        tests/l1_collect/test_run_incremental.py
git commit -m "feat(l1): run_incremental方法本体(level过滤+gate接线+软锁+quarantine)"
```

---

## Task 8: audit_coverage.py — 覆盖审计

**Files:**
- Create: `scripts/l1_collect/audit_coverage.py`
- Test: `tests/l1_collect/test_audit_coverage.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/l1_collect/test_audit_coverage.py
import datetime


def test_zero_alert_for_key_province_theme():
    from scripts.l1_collect.audit_coverage import get_zero_alerts
    m = {"江苏省": {"充电": 0, "加油": 3, "电力": 5}}
    a = get_zero_alerts(m)
    assert any(x["province"] == "江苏省" and x["theme"] == "充电" for x in a)


def test_no_zero_alert_when_covered():
    from scripts.l1_collect.audit_coverage import get_zero_alerts
    assert get_zero_alerts({"广东省": {"充电": 12, "加油": 8, "电力": 15}}) == []


def test_freshness_flags_stale():
    from scripts.l1_collect.audit_coverage import check_freshness
    old = (datetime.date.today() - datetime.timedelta(days=70)).isoformat()
    new = datetime.date.today().isoformat()
    a = check_freshness({"吉林省": old, "广东省": new}, stale_days=60)
    assert any(x["province"] == "吉林省" for x in a)
    assert all(x["province"] != "广东省" for x in a)


def test_gap_diagnosis_collection_vs_attribution():
    from scripts.l1_collect.audit_coverage import diagnose_gap
    # 该省该渠道扫描数=0 → 采集缺口
    assert diagnose_gap("江苏省", "充电", scanned_count=0)["cause"] == "collection_gap"
    # 扫到了但矩阵为0 → 归属错标
    assert diagnose_gap("江苏省", "充电", scanned_count=40)["cause"] == "attribution_gap"


def test_html_report_marks_zero():
    from scripts.l1_collect.audit_coverage import render_html_report
    html = render_html_report({"江苏省": {"充电": 0, "加油": 3, "电力": 7}},
                              alerts=[], freshness={})
    assert "<table" in html and "江苏" in html
    assert 'class="zero"' in html
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_collect/test_audit_coverage.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现 audit_coverage.py**

```python
# scripts/l1_collect/audit_coverage.py
"""L1覆盖审计:省×主题矩阵+零覆盖告警+新鲜度+缺口归因+HTML。
指标LLM设计一次→固化为规则(不每次调LLM防漂移)。"""
from __future__ import annotations
import argparse
import datetime
import re
from collections import defaultdict
from pathlib import Path

VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
BV_DIR = VAULT / "_meta" / "business_view"
POLICIES_DIR = VAULT / "0_raw" / "policies"
STALE_DAYS = 60
THEMES = ["充电", "加油", "电力"]
KEY_PROVINCES = {"广东省", "江苏省", "浙江省", "山东省", "四川省", "河南省", "湖北省",
                 "湖南省", "安徽省", "河北省", "福建省", "上海市", "北京市", "重庆市"}


def compute_coverage_matrix(bv_dir: Path) -> dict:
    import yaml
    m = defaultdict(lambda: defaultdict(int))
    if not bv_dir.exists():
        return {}
    for f in bv_dir.glob("*.yaml"):
        try:
            bv = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        region = bv.get("region") or ""
        prov = region.split("/")[0].strip() if region else ""
        themes = bv.get("themes") or []
        if not prov:
            continue
        for t in THEMES:
            if any(t in th for th in themes):
                m[prov][t] += 1
    return {p: dict(v) for p, v in m.items()}


def get_zero_alerts(matrix: dict) -> list:
    out = []
    for prov in KEY_PROVINCES:
        for t in THEMES:
            if matrix.get(prov, {}).get(t, 0) == 0:
                out.append({"province": prov, "theme": t, "count": 0, "severity": "HIGH"})
    return out


def diagnose_gap(province: str, theme: str, scanned_count: int) -> dict:
    cause = "collection_gap" if scanned_count == 0 else "attribution_gap"
    action = (f"补采 {province} {theme} 渠道" if cause == "collection_gap"
              else f"复查 {province} 已采政策的 region/theme 标注(回灌②)")
    return {"province": province, "theme": theme, "cause": cause, "action": action}


def compute_freshness(policies_dir: Path) -> dict:
    fresh: dict = {}
    DATE = re.compile(r"fetched_at:\s*(.+)")
    REGION = re.compile(r"^region:\s*(.+)", re.M)
    for p in policies_dir.glob("*.md"):
        try:
            c = p.read_text(encoding="utf-8")
        except Exception:
            continue
        md, mr = DATE.search(c), REGION.search(c)
        if not (md and mr):
            continue
        d = md.group(1).strip()[:10]
        prov = mr.group(1).strip().split("/")[0]
        if prov and (prov not in fresh or d > fresh[prov]):
            fresh[prov] = d
    return fresh


def check_freshness(freshness: dict, stale_days: int = STALE_DAYS) -> list:
    cutoff = (datetime.date.today() - datetime.timedelta(days=stale_days)).isoformat()
    return [{"province": p, "last_date": d, "severity": "WARN"}
            for p, d in freshness.items() if d < cutoff]


def render_html_report(matrix: dict, alerts: list, freshness: dict) -> str:
    provs = sorted(set(matrix) | set(freshness))
    cutoff = (datetime.date.today() - datetime.timedelta(days=STALE_DAYS)).isoformat()
    rows = ""
    for prov in provs:
        bold = "font-weight:bold" if prov in KEY_PROVINCES else ""
        cells = ""
        for t in THEMES:
            n = matrix.get(prov, {}).get(t, 0)
            cls = ' class="zero"' if n == 0 else ""
            cells += f'<td{cls}>{n}</td>'
        fr = freshness.get(prov, "—")
        fcls = ' style="color:red"' if fr != "—" and fr < cutoff else ""
        rows += f'<tr><td style="{bold}">{prov}</td>{cells}<td{fcls}>{fr}</td></tr>'
    alert_html = ""
    if alerts:
        lis = "".join(f"<li>[{a.get('severity','')}] {a.get('province','')} "
                      f"{a.get('theme','')}</li>" for a in alerts)
        alert_html = f"<h2>告警({len(alerts)})</h2><ul>{lis}</ul>"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>L1覆盖审计</title>
<style>table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:4px 8px}}
th{{background:#eee}}.zero{{background:#fcc}}</style></head><body>
<h1>L1采集覆盖审计 — {datetime.date.today()}</h1>{alert_html}
<h2>省×主题矩阵</h2><table>
<tr><th>省</th>{''.join(f'<th>{t}</th>' for t in THEMES)}<th>最后采集</th></tr>
{rows}</table>
<p>加粗=重点省 / 红底=零覆盖 / 红字=超{STALE_DAYS}天未采</p></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="state/l1_gate/audit_coverage.html")
    a = ap.parse_args()
    matrix = compute_coverage_matrix(BV_DIR)
    fresh = compute_freshness(POLICIES_DIR)
    alerts = get_zero_alerts(matrix) + check_freshness(fresh)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html_report(matrix, alerts, fresh), encoding="utf-8")
    print(f"[audit] 省份={len(matrix)} 告警={len(alerts)} → {out}")
    for z in get_zero_alerts(matrix):
        print(f"  零覆盖 {z['province']} {z['theme']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_collect/test_audit_coverage.py -v`
Expected: PASS

- [ ] **Step 5: 全量单测回归 + Commit**

```bash
python -m pytest tests/l1_collect/ -v   # 期望: 全绿
git add scripts/l1_collect/audit_coverage.py tests/l1_collect/test_audit_coverage.py
git commit -m "feat(l1): 覆盖审计(省×主题矩阵+零覆盖+新鲜度+缺口归因+HTML)"
```

---

## Task 9 (ops·B类): golden 构建 + gate 校准

**验收 = planted-recall ≥ 0.9。** 这是质量门上岗的硬门。

- [ ] **Step 1: 写 golden 抽样脚本**

```python
# scripts/_oneshot/build_l1_golden.py
"""golden:好政策25(vault抽body长)+非政策25(b7已知)+埋10 planted。"""
from __future__ import annotations
import json, random
from pathlib import Path

VAULT = Path.home() / "Documents/Zayn Main/政策分析"
POL = VAULT / "0_raw/policies"
B7 = Path("state/node3c/sem_preview_20260606/b7_contamination.jsonl")  # 65条已知非政策
OUT = Path("state/l1_gate/golden"); OUT.mkdir(parents=True, exist_ok=True)
random.seed(42)


def _fields(p: Path, gold: str, planted: bool, note: str):
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    title = next((l.lstrip("# ").strip() for l in lines if l.strip().startswith("#")), p.stem)
    url = next((l.split(":", 1)[-1].strip() for l in lines
                if l.startswith("source_url:") or "url:" in l), "")
    body_head = "\n".join(lines[8:28])
    return {"pid": p.stem, "url": url, "title": title, "body_head": body_head,
            "gold_label": gold, "is_planted": planted, "notes": note}


good = [p for p in POL.glob("*.md") if not p.name.startswith("_") and p.stat().st_size > 2500]
sg = random.sample(good, 25)
bad_pids = ([json.loads(l)["pid"] for l in B7.read_text().splitlines() if l.strip()]
            if B7.exists() else [])
sb = [POL / f"{pid}.md" for pid in bad_pids if (POL / f"{pid}.md").exists()][:25]

recs = [_fields(p, "policy", False, "") for p in sg]
recs += [_fields(p, "non_policy_index", False, "b7_nonpolicy") for p in sb]
# 埋错:5好→谎称非政策,5坏→谎称政策
for r in [x for x in recs if x["gold_label"] == "policy"][:5]:
    r["is_planted"], r["gold_label"] = True, "non_policy_news"
for r in [x for x in recs if x["gold_label"] != "policy" and not x["is_planted"]][:5]:
    r["is_planted"], r["gold_label"] = True, "policy"

out = OUT / "golden_v1.jsonl"
out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
print(f"golden {len(recs)} (planted={sum(r['is_planted'] for r in recs)}) → {out}")
```

Run: `cd ~/dev/政策分析-pipeline-l1-repair && python3 -m scripts._oneshot.build_l1_golden`
Expected: 输出 `golden 50 (planted=10) → ...`，planted ≥ 8

- [ ] **Step 2: 跑 gate 校准（B 类阈值断言）**

```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=$DEEPSEEK_API_KEY \
python3 -c "
import json
from pathlib import Path
from scripts.l1_collect.policy_gate import gate_one, GoldenRecord
from scripts.common.llm import OpenAICompatClient
cli = OpenAICompatClient(model='deepseek-v4-flash', log_path='state/l1_gate/calib_calls.jsonl')
G = [GoldenRecord(**json.loads(l)) for l in
     Path('state/l1_gate/golden/golden_v1.jsonl').read_text().splitlines() if l.strip()]
planted = [r for r in G if r.is_planted]
res = [gate_one(r.pid, r.url, r.title, r.body_head, cli.complete) for r in planted]
rec = sum(1 for r, x in zip(planted, res) if x.label != 'policy')
recall = rec / len(planted)
print(f'planted-recall: {recall:.2%} ({rec}/{len(planted)})')
Path('state/l1_gate/gate_calibration.json').write_text(
    json.dumps({'planted_recall': recall, 'pass': recall >= 0.9}, indent=2))
print('PASS' if recall >= 0.9 else 'FAIL — 调 policy_gate._SYSTEM prompt 重跑(≤4次)')
"
```
Expected: `planted-recall ≥ 0.9` → PASS。不达标 → 改 `policy_gate._SYSTEM` 重跑（≤4 次）。

- [ ] **Step 3: Commit**

```bash
git add scripts/_oneshot/build_l1_golden.py
git add -f state/l1_gate/golden/golden_v1.jsonl state/l1_gate/gate_calibration.json
git commit -m "feat(l1·ops): gate golden 50 + 校准 planted-recall≥0.9"
```

---

## Task 10 (ops·B类): 小切片验证 + CHECKPOINT

- [ ] **Step 1: 发现国家级 + 大省渠道（写 catalog）**

```python
# scripts/_oneshot/expand_channels_2026-06-06.py
"""发现国家13 + 省级渠道,probe验证,幂等append到catalog。"""
from __future__ import annotations
from pathlib import Path
from scripts.l1_collect.channel_discovery import (
    NATIONAL_TARGETS, province_targets_from_registry, discover_one)
from scripts.l1_collect.channel_catalog import load_catalog, save_catalog

CAT = Path("state/T1_channels/channel_catalog.yaml")
REG = Path.home() / "Documents/Zayn Main/政策分析/_meta/channel_registry.yaml"
existing = load_catalog(CAT)
have = {c.root_domain for c in existing}
targets = NATIONAL_TARGETS + province_targets_from_registry(REG)
added = []
for t in targets:
    if t["root_domain"] in have:
        continue
    ch = discover_one(t)
    if ch:
        added.append(ch)
        print(f"  {ch.level:4s} {ch.root_domain:30s} {ch.status.value} {ch.list_url}")
save_catalog(existing + added, CAT)
v = sum(1 for c in added if c.status.value == "验证")
print(f"新增 {len(added)} 验证 {v}")
```

Run（需 env）:
```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=$DEEPSEEK_API_KEY \
python3 -m scripts._oneshot.expand_channels_2026-06-06
```
Expected（B 类阈值）: 国家级验证渠道 ≥ 8（数 catalog：`grep -c "level: 国家" state/T1_channels/channel_catalog.yaml`）

- [ ] **Step 2: 小切片端到端真跑（国家级，非 dry-run）**

```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=$DEEPSEEK_API_KEY \
JUDGE_MODEL=deepseek-v4-flash FIRECRAWL_API_KEY=$FIRECRAWL_API_KEY \
python3 -m scripts.l1_collect.run_incremental --level national --since 2026-01-01
```
Expected（B 类）: `total_ingested > 0`，gate_rejected 有数（门在工作）

- [ ] **Step 3: 生成 checkpoint 审阅样本**

```bash
echo "=== 发现的列表页URL(人工核对正确性) ===" > state/l1_gate/checkpoint.txt
grep -A1 "level: 国家" state/T1_channels/channel_catalog.yaml | grep list_url >> state/l1_gate/checkpoint.txt
echo "=== 本切片新入库 raw(抽查召回质量) ===" >> state/l1_gate/checkpoint.txt
ls -t "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies" | head -20 >> state/l1_gate/checkpoint.txt
echo "=== gate reject 抽样(精度) ===" >> state/l1_gate/checkpoint.txt
tail -15 state/T1_incremental/quar/gate_rejects.jsonl >> state/l1_gate/checkpoint.txt
cat state/l1_gate/checkpoint.txt
```

- [ ] **Step 4: 【CHECKPOINT — 停，交用户审】**

向用户呈报三样：① 发现的列表页 URL 对不对；② 新入库 raw 的召回质量（是不是真政策、漏没漏）；③ gate reject 抽样的精度（误杀没有）。**用户确认通过后才进 Task 11 全量 backfill。** 不通过 → 回退对应 Task 调整。

---

## Task 11 (ops·B类): 全量 backfill（孤儿化）

**前置: Task 10 CHECKPOINT 已通过。**

- [ ] **Step 1: 发现全省 31 + 重点 48 渠道**

补 `expand_channels` 覆盖 city_priority 的 48 城（`province_targets` 已含省级；城市渠道从现有 catalog 705 候选里 probe 验证 + discovery 补缺）。Run 后验证：`市级验证渠道 ≥ 48`。

```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=$DEEPSEEK_API_KEY \
python3 -m scripts._oneshot.expand_channels_2026-06-06
grep -c "status: 验证" state/T1_channels/channel_catalog.yaml
```

- [ ] **Step 2: 全量 backfill（孤儿化 nohup）**

```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=$DEEPSEEK_API_KEY \
JUDGE_MODEL=deepseek-v4-flash FIRECRAWL_API_KEY=$FIRECRAWL_API_KEY \
nohup caffeinate -i python3 -m scripts.l1_collect.run_incremental \
  --level national,province,city --since 2026-01-01 \
  >state/l1_gate/backfill_2026-06-06.log 2>&1 & disown
echo "PID $!"
```
监控: `tail -f state/l1_gate/backfill_2026-06-06.log`；结束标志 = log 尾出现 `[run_incremental] DONE`。

- [ ] **Step 3: 重抓被截断的政策母文件（门后）**

```python
# scripts/_oneshot/run_pdf_refetch_2026-06-06.py
"""重抓 body<800 的政策(谓词候选,单调护栏在 upgrade 内)。"""
from __future__ import annotations
import json
from pathlib import Path
from scripts.l1_collect.pdf_refetch import should_refetch, upgrade_policy_body

POL = Path.home() / "Documents/Zayn Main/政策分析/0_raw/policies"
LOG = Path("state/l1_gate/pdf_refetch_2026-06-06.jsonl")
LOG.parent.mkdir(parents=True, exist_ok=True)
thin = [p for p in POL.glob("*.md") if not p.name.startswith("_") and should_refetch(p)]
print(f"薄文件 {len(thin)}")
res = []
for p in thin:
    r = upgrade_policy_body(p); r["pid"] = p.stem; res.append(r)
    print(f"  {'✅' if r['upgraded'] else '·'} {p.stem[:45]} {r.get('old_chars','?')}→{r.get('new_chars','?')}")
LOG.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in res) + "\n")
print(f"升级 {sum(1 for r in res if r['upgraded'])}/{len(thin)}")
```

```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
FIRECRAWL_API_KEY=$FIRECRAWL_API_KEY \
nohup caffeinate -i python3 -m scripts._oneshot.run_pdf_refetch_2026-06-06 \
  >state/l1_gate/pdf_refetch.log 2>&1 & disown
```
Expected（B 类·护栏验收）: 日志中无 raw 被缩短——`grep -c '"not_longer"' state/l1_gate/pdf_refetch_2026-06-06.jsonl` 是 skip 计数；`upgraded:true` 的均满足 new>old。

---

## Task 12 (ops): 收口

- [ ] **Step 1: 覆盖审计前后对比**

```bash
python3 -m scripts.l1_collect.audit_coverage --out state/l1_gate/audit_post_2026-06-06.html
open state/l1_gate/audit_post_2026-06-06.html
```
Expected（B 类·核心验收）: 江苏/浙江/四川 充电覆盖 `0 → >0`（对比 backfill 前）。

- [ ] **Step 2: 退残留非政策（走 quarantine，不删）**

gate_rejects 已在 `state/T1_incremental/quar/gate_rejects.jsonl`。对 vault 现存 ~43 旧残留：跑 `policy_gate.gate_corpus` 标记 → 移到 `vault 0_raw/_archive/policies/gate_residue_2026-06-06/`（move 非 delete，记 README）。

- [ ] **Step 3: 八步采集法 doc 标注**

在 `策略-八步采集法` 顶部加 header：「⚠ 加工逻辑已剥离;L1 采集 SOP 重生为可执行 `scripts/l1_collect/run_incremental.py`，范围口径下调对齐决策A(国家+省31+重点48)」。不重写正文（防推倒重来）。

- [ ] **Step 4: Commit 两仓**

```bash
# vault(raw新增/重抓/退残留 — 先tag后commit)
cd "/Users/shaoziyuan/Documents/Zayn Main/政策分析"
git tag pre-l1-backfill-2026-06-06 2>/dev/null || true
git add 0_raw/ && git commit -m "feat(vault): L1全量backfill+母文件重抓+退残留非政策(2026-06-06)"
# pipeline(代码+ops脚本+catalog+审计报告)
cd ~/dev/政策分析-pipeline-l1-repair
git add scripts/ tests/ state/T1_channels/channel_catalog.yaml
git add -f state/l1_gate/audit_post_2026-06-06.html
git commit -m "feat(l1): 全量backfill收口(覆盖审计前后对比+catalog+ops脚本)"
```

- [ ] **Step 5: 最终验收清单**

```bash
cd ~/dev/政策分析-pipeline-l1-repair
python -m pytest tests/l1_collect/ -v                              # 全绿
grep -c "level: 国家" state/T1_channels/channel_catalog.yaml        # ≥8
grep -c "status: 验证" state/T1_channels/channel_catalog.yaml       # 国≥8 省≥20 市≥48
python3 -c "import json; d=json.load(open('state/l1_gate/gate_calibration.json')); assert d['pass']"  # recall≥0.9
grep -c '"not_longer"' state/l1_gate/pdf_refetch_2026-06-06.jsonl   # 护栏skip计数(无raw缩短)
```

---

## Deferred / 不在本线（spec §6）
- **TODO-A 微信公众号政策评论**(commentary·RSS自动化问题)→ 政策采集跑完后,挂 B3。
- **TODO-B 零散行业情报**(market intel)→ 不专抓;gate reject 走 quarantine 保住误抓项,挂 B1。

## 自审（spec 覆盖 + 一致性）
- spec §3.1 渠道发现 → Task 3 ✓ / §3.2 分层扫 → Task 4 ✓ / §3.3 firecrawl → Task 1 ✓ / §3.4 gate+golden → Task 5,9 ✓ / §3.5 重抓护栏 → Task 6,11 ✓ / §3.6 run_incremental → Task 7 ✓ / §3.7 审计+归因 → Task 8,12 ✓ / §4 执行序 → Task 9-12 ✓ / §6 Deferred → 本节 ✓
- 类型一致:`GateResult.action ∈ {pass,reject,review_queue}` 全 plan 统一;`Channel` 字段对齐现有 `channel_catalog.py`;`discover_one`/`gate_one`/`upgrade_policy_body` 签名跨任务一致。
