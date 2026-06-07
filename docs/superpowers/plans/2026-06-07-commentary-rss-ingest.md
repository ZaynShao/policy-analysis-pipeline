# Commentary RSS 自动入库闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 wewe-rss 抓到的微信公众号文章自动入库到 vault `0_raw/commentaries/`,做成可在国内节点定时跑的 L1 评论采集闭环,token 失效时告警。

**Architecture:** 消费 wewe-rss 的 JSON feed(β,`FEED_MODE=fulltext` 已含全文)→ 统一结构性过滤(SKIP / market_intel 路由,账号无关)→ 写 Mac vault(仅追加,确定性 frontmatter,不写 LLM 判定)→ 记 processed ledger + last_run。路径/凭据全 env/CLI 注入,零硬编码,便于后续迁国内容器。

**Tech Stack:** Python 3.9+,requests(取 feed/兜底抓正文),trafilatura+bs4(HTML→文本),pyyaml(frontmatter),sqlite3(token 健康检查,标准库),pytest。**不加 feedparser**(用 JSON feed 纯 json 解析)。

**spec:** `docs/superpowers/specs/2026-06-07-commentary-rss-ingest-design.md`

---

## File Structure

新增一个自包含子包 `scripts/l1_collect/commentary_ingest/`,与现有 l1_collect 平级隔离(纪律:只新增不改已有):

```
scripts/l1_collect/commentary_ingest/
  __init__.py
  models.py          # FeedItem / Disposition / Classification 数据类(全包共享)
  feed_client.py     # 取 wewe-rss JSON feed + 解析成 FeedItem 列表
  content.py         # FeedItem.content_html → 纯文本 body;feed 缺正文时兜底抓 URL(限速/退避)
  filters.py         # classify(item)→Disposition:统一结构性过滤(SKIP / market_intel)
  writer.py          # 写 vault commentary md / market_intel staging json(仅追加,schema 合规)
  ledger.py          # 已见 url 集合(vault+ledger 去重)+ 处置记录 + last_run
  token_health.py    # 读 sqlite accounts.status 检测 token 失效 + 告警
  run.py             # CLI 编排:--feed-url/--vault-dir/--state-dir/--db-path/--check-token

tests/l1_collect/commentary_ingest/
  __init__.py
  fixtures/
    feed_sample.json         # 从真实 wewe-rss 捕获的 JSON feed 样本(Task 1)
  test_feed_client.py
  test_content.py
  test_filters.py
  test_writer.py
  test_ledger.py
  test_token_health.py
  test_run.py

docker/wewe-rss/compose.yml                          # 阶段二:容器定义
docs/runbooks/commentary-rss-ingest-migration.md     # 阶段二:Mac→国内容器迁移
```

CLAUDE.md(项目根)追加"评论 RSS 迁移方法摘要"——见 Task 11。

---

## Task 1: 包骨架 + state 放行 + 捕获真实 feed fixture

**Files:**
- Create: `scripts/l1_collect/commentary_ingest/__init__.py`(空)
- Create: `tests/l1_collect/commentary_ingest/__init__.py`(空)
- Create: `tests/l1_collect/__init__.py`(若不存在)
- Create: `tests/l1_collect/commentary_ingest/fixtures/feed_sample.json`
- Modify: `state/.gitignore`(放行 commentary_ingest 子目录的 ledger/last_run,**不放行**正文 staging)

- [ ] **Step 1: 建空包文件**

```bash
mkdir -p scripts/l1_collect/commentary_ingest tests/l1_collect/commentary_ingest/fixtures
touch scripts/l1_collect/commentary_ingest/__init__.py
touch tests/l1_collect/commentary_ingest/__init__.py
[ -f tests/l1_collect/__init__.py ] || touch tests/l1_collect/__init__.py
```

- [ ] **Step 2: 启动本机 wewe-rss 并捕获真实 feed**

> wewe-rss 即使 token 失效,仍能 serve 已存 2479 篇文章的 feed(token 只用于发现新文章)。先确认 Docker Desktop 已启动。

Run:
```bash
docker rm -f wewe-rss 2>/dev/null
docker run -d --name wewe-rss -p 4000:4000 \
  -e DATABASE_TYPE=sqlite -e AUTH_CODE=zayn-policy-2026 \
  -e SERVER_ORIGIN_URL=http://localhost:4000 \
  -e FEED_MODE=fulltext -e ENABLE_CLEAN_HTML=true \
  -v ~/wewe-rss-data:/app/data --restart unless-stopped \
  cooderl/wewe-rss-sqlite:latest
sleep 8
# 全部公众号合并 feed 的 JSON 形式,取前若干条做样本
curl -s 'http://localhost:4000/feeds/all.json?limit=8' \
  -H 'Authorization: Bearer zayn-policy-2026' \
  -o tests/l1_collect/commentary_ingest/fixtures/feed_sample.json
python3 -m json.tool tests/l1_collect/commentary_ingest/fixtures/feed_sample.json | head -40
```

Expected:JSON Feed 1.1 结构,顶层有 `version`/`title`/`items[]`;每 item 含 `id`(22 位 hash)、`url`(`https://mp.weixin.qq.com/s/{id}`)、`title`、`content_html`(fulltext 模式下非空)、`date_published`、`authors[0].name`(公众号名)。

> **若实际字段名与上不符**(如 `content_text` / `author`),以**捕获到的真实结构为准**,后续 Task 2 的解析按真实字段写。若 `all.json` 端点不存在,改用单 feed:先 `curl -s http://localhost:4000/feeds.json -H 'Authorization: Bearer zayn-policy-2026'` 拿某 feed id,再 `curl .../feeds/{id}.json`。
>
> **若执行环境无 Docker**:手工按上述 Expected 结构 + 本仓已知真实数据(如 `id=tQnDiszHVcjKkO8nv2JulA` → `绿色金融日报4.28` → 中央财经大学绿色金融国际研究院)造一份 ≥6 条的 fixture,覆盖:正常 commentary、市场行情(中标/GWh)、招聘/节日噪音、空 content_html 各至少 1 条。

- [ ] **Step 3: state/.gitignore 放行 commentary_ingest(只放行台账,不放行正文)**

在 `state/.gitignore` 末尾追加:

```
# commentary_ingest:放行台账与状态,不放行正文 staging(原文不进 git)
!commentary_ingest/
!commentary_ingest/processed_ids.jsonl
!commentary_ingest/last_run.json
!commentary_ingest/.gitkeep
```

- [ ] **Step 4: 建 state 目录占位**

```bash
mkdir -p state/commentary_ingest
touch state/commentary_ingest/.gitkeep
```

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/commentary_ingest tests/l1_collect state/.gitignore state/commentary_ingest/.gitkeep
git commit -m "feat(commentary-ingest): 包骨架 + state 放行 + 真实 feed fixture"
```

---

## Task 2: 数据模型 + feed 解析

**Files:**
- Create: `scripts/l1_collect/commentary_ingest/models.py`
- Create: `scripts/l1_collect/commentary_ingest/feed_client.py`
- Test: `tests/l1_collect/commentary_ingest/test_feed_client.py`

- [ ] **Step 1: 写数据模型**(无测试,纯定义)

`scripts/l1_collect/commentary_ingest/models.py`:

```python
"""commentary_ingest 全包共享数据类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass
class FeedItem:
    """一条 wewe-rss feed 文章(已解析)。"""
    id: str                 # 22 位微信短链 hash
    url: str                # https://mp.weixin.qq.com/s/{id}
    title: str
    content_html: str       # fulltext 模式下的正文 HTML;可能为空
    date_published: str     # YYYY-MM-DD,缺失为 ""
    source_account: str     # 公众号名


class Disposition(str, Enum):
    INGEST = "ingest"            # 入 vault commentaries
    SKIP_JUNK = "skip_junk"      # 完全丢弃
    MARKET_INTEL = "market_intel"  # 暂存 state,等 B1


@dataclass
class Classification:
    disposition: Disposition
    reasons: list = field(default_factory=list)
```

- [ ] **Step 2: 写 feed 解析失败测试**

`tests/l1_collect/commentary_ingest/test_feed_client.py`:

```python
import json
from pathlib import Path

from scripts.l1_collect.commentary_ingest.feed_client import parse_feed

FIXTURE = Path(__file__).parent / "fixtures" / "feed_sample.json"


def test_parse_feed_returns_feeditems_from_real_fixture():
    items = parse_feed(FIXTURE.read_text(encoding="utf-8"))
    assert len(items) >= 1
    first = items[0]
    assert len(first.id) == 22
    assert first.url == f"https://mp.weixin.qq.com/s/{first.id}"
    assert first.title
    assert first.source_account


def test_parse_feed_normalizes_date_to_yyyy_mm_dd():
    raw = json.dumps({
        "version": "https://jsonfeed.org/version/1.1",
        "items": [{
            "id": "tQnDiszHVcjKkO8nv2JulA",
            "url": "https://mp.weixin.qq.com/s/tQnDiszHVcjKkO8nv2JulA",
            "title": "绿色金融日报4.28",
            "content_html": "<p>正文</p>",
            "date_published": "2026-04-28T13:13:41+08:00",
            "authors": [{"name": "中央财经大学绿色金融国际研究院"}],
        }],
    })
    items = parse_feed(raw)
    assert items[0].date_published == "2026-04-28"
    assert items[0].source_account == "中央财经大学绿色金融国际研究院"


def test_parse_feed_empty_items_returns_empty_list():
    assert parse_feed('{"version":"x","items":[]}') == []
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_feed_client.py -v`
Expected: FAIL,`ModuleNotFoundError: ... feed_client`

- [ ] **Step 4: 实现 feed_client**

`scripts/l1_collect/commentary_ingest/feed_client.py`:

```python
"""取 wewe-rss JSON feed 并解析成 FeedItem 列表。

接口契约:wewe-rss JSON Feed 1.1。字段以 Task 1 捕获的真实结构为准;
本实现对 content_html/content_text、authors/author 做兼容兜底。
"""
from __future__ import annotations

import json

import requests

from .models import FeedItem

WEIXIN_PERMALINK = "https://mp.weixin.qq.com/s/{}"


def _norm_date(raw: str) -> str:
    """ISO datetime / date → YYYY-MM-DD;无法解析返回 ''。"""
    if not raw:
        return ""
    return str(raw)[:10] if len(str(raw)) >= 10 else ""


def _account_name(item: dict) -> str:
    authors = item.get("authors")
    if isinstance(authors, list) and authors and isinstance(authors[0], dict):
        return authors[0].get("name", "") or ""
    author = item.get("author")
    if isinstance(author, dict):
        return author.get("name", "") or ""
    return item.get("author_name", "") or ""


def _content(item: dict) -> str:
    return item.get("content_html") or item.get("content_text") or ""


def parse_feed(json_text: str) -> list:
    """JSON feed 文本 → list[FeedItem]。"""
    data = json.loads(json_text)
    out = []
    for item in data.get("items", []):
        aid = item.get("id", "")
        # 容错:某些 feed 的 id 是整段 url,抽末段 hash
        if "/" in aid:
            aid = aid.rstrip("/").split("/")[-1]
        url = item.get("url") or WEIXIN_PERMALINK.format(aid)
        out.append(FeedItem(
            id=aid,
            url=url,
            title=(item.get("title") or "").strip(),
            content_html=_content(item),
            date_published=_norm_date(item.get("date_published", "")),
            source_account=_account_name(item),
        ))
    return out


def fetch_feed(feed_url: str, auth_code: str = "", timeout: int = 30) -> list:
    """HTTP 拉 feed → list[FeedItem]。auth_code 走 Bearer 头。"""
    headers = {"Authorization": f"Bearer {auth_code}"} if auth_code else {}
    resp = requests.get(feed_url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return parse_feed(resp.text)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_feed_client.py -v`
Expected: PASS(3 passed)。若真实 fixture 字段名不同,按真实结构调 `_content`/`_account_name` 再过。

- [ ] **Step 6: 提交**

```bash
git add scripts/l1_collect/commentary_ingest/models.py scripts/l1_collect/commentary_ingest/feed_client.py tests/l1_collect/commentary_ingest/test_feed_client.py
git commit -m "feat(commentary-ingest): FeedItem 模型 + JSON feed 解析"
```

---

## Task 3: 内容提取 + 兜底抓取

**Files:**
- Create: `scripts/l1_collect/commentary_ingest/content.py`
- Test: `tests/l1_collect/commentary_ingest/test_content.py`

- [ ] **Step 1: 写测试**

`tests/l1_collect/commentary_ingest/test_content.py`:

```python
from scripts.l1_collect.commentary_ingest.content import html_to_text, to_body
from scripts.l1_collect.commentary_ingest.models import FeedItem


def _item(content_html="", url="https://mp.weixin.qq.com/s/" + "a" * 22):
    return FeedItem(id="a" * 22, url=url, title="标题",
                    content_html=content_html, date_published="2026-04-28",
                    source_account="某号")


def test_html_to_text_strips_tags():
    text = html_to_text("<p>第一段</p><p>第二段</p>")
    assert "第一段" in text and "第二段" in text
    assert "<p>" not in text


def test_to_body_uses_feed_content_when_present():
    long_html = "<p>" + ("有效正文内容。" * 50) + "</p>"
    body, src = to_body(_item(content_html=long_html), fetch_fallback=False)
    assert "有效正文内容" in body
    assert src == "feed"


def test_to_body_marks_empty_when_no_content_and_no_fallback():
    body, src = to_body(_item(content_html=""), fetch_fallback=False)
    assert src == "empty"
    assert body == ""


def test_to_body_short_content_triggers_empty_without_fallback():
    body, src = to_body(_item(content_html="<p>短</p>"), fetch_fallback=False,
                        min_len=200)
    assert src == "empty"
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_content.py -v`
Expected: FAIL,`ModuleNotFoundError: ... content`

- [ ] **Step 3: 实现 content.py**

`scripts/l1_collect/commentary_ingest/content.py`:

```python
"""FeedItem 正文提取:优先用 feed 全文;缺失/过短时兜底抓 URL(限速/退避)。

§6.2:正文兜底抓取走 mp.weixin.qq.com,限速 + 随机延迟 + 退避;失败标记不硬刚。
随机延迟用 time.sleep,延迟量由调用方按 index 错开(本模块固定区间)。
"""
from __future__ import annotations

import time

import requests
import trafilatura
from bs4 import BeautifulSoup

from .models import FeedItem

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def html_to_text(html: str) -> str:
    """HTML → 纯文本。trafilatura 优先,bs4 兜底。"""
    if not html:
        return ""
    extracted = trafilatura.extract(html, include_comments=False,
                                    include_tables=False)
    if extracted and extracted.strip():
        return extracted.strip()
    return BeautifulSoup(html, "html.parser").get_text("\n").strip()


def _refetch(url: str, timeout: int, delay: float) -> str:
    """限速兜底抓正文;任何失败返回 ''。"""
    time.sleep(delay)
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        return ""
    return html_to_text(resp.text)


def to_body(item: FeedItem, *, fetch_fallback: bool = True,
            min_len: int = 200, timeout: int = 30,
            delay: float = 4.0) -> tuple:
    """返回 (body, source)。source ∈ {'feed','refetch','empty'}。"""
    body = html_to_text(item.content_html)
    if len(body) >= min_len:
        return body, "feed"
    if fetch_fallback:
        refetched = _refetch(item.url, timeout, delay)
        if len(refetched) >= min_len:
            return refetched, "refetch"
    return "", "empty"
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_content.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/commentary_ingest/content.py tests/l1_collect/commentary_ingest/test_content.py
git commit -m "feat(commentary-ingest): 正文提取 + 限速兜底抓取"
```

---

## Task 4: 结构性过滤(SKIP / market_intel,统一规则)

**Files:**
- Create: `scripts/l1_collect/commentary_ingest/filters.py`
- Test: `tests/l1_collect/commentary_ingest/test_filters.py`

- [ ] **Step 1: 写测试**

`tests/l1_collect/commentary_ingest/test_filters.py`:

```python
from scripts.l1_collect.commentary_ingest.filters import classify
from scripts.l1_collect.commentary_ingest.models import Disposition, FeedItem


def _item(title):
    return FeedItem(id="a" * 22, url="u", title=title, content_html="x",
                    date_published="2026-04-28", source_account="某号")


def test_recruitment_is_skipped():
    assert classify(_item("诚聘英才|2026校园招聘启动")).disposition == Disposition.SKIP_JUNK


def test_holiday_greeting_is_skipped():
    assert classify(_item("端午节快乐，放假通知")).disposition == Disposition.SKIP_JUNK


def test_pure_video_is_skipped():
    assert classify(_item("视频：花香柳马焕新城市生态")).disposition == Disposition.SKIP_JUNK


def test_procurement_with_capacity_is_market_intel():
    c = classify(_item("0.71元Wh，河北200MW800MWh储能项目EPC中标公示"))
    assert c.disposition == Disposition.MARKET_INTEL


def test_bidding_announcement_is_market_intel():
    assert classify(_item("浙江温州工商储设备招标公告")).disposition == Disposition.MARKET_INTEL


def test_ipo_financing_is_market_intel():
    assert classify(_item("晶科科技完成近2亿元融资")).disposition == Disposition.MARKET_INTEL


def test_normal_commentary_is_ingested():
    c = classify(_item("IIGF观点 | 可持续信息披露规则趋同下的制度比较与中国路径"))
    assert c.disposition == Disposition.INGEST
    assert c.reasons == []


def test_policy_interpretation_is_ingested():
    assert classify(_item("解读丨2025年两新政策如何加力扩围")).disposition == Disposition.INGEST
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_filters.py -v`
Expected: FAIL,`ModuleNotFoundError: ... filters`

- [ ] **Step 3: 实现 filters.py**

`scripts/l1_collect/commentary_ingest/filters.py`:

```python
"""统一结构性过滤(账号无关,不打 per-account 补丁)。

两层(spec §5):
  1. SKIP_JUNK:招聘 / 节日 / 纯视频 / 活动征集 —— 完全丢弃
  2. MARKET_INTEL:采购招标+容量数字 / IPO融资 / 出货数据 —— 暂存等 B1
其余 → INGEST(保守多收,相关性留 L2)。

只看 title;不做能源相关性判断(那是 L2)。
"""
from __future__ import annotations

import re

from .models import Classification, Disposition, FeedItem

SKIP_PATTERNS = [
    (re.compile(r"招聘|诚聘|岗位招募|招募"), "招聘"),
    (re.compile(r"节快乐|放假通知|假期安排|祝.{0,4}节"), "节日"),
    (re.compile(r"^视频[：:]|^\s*视频\s*[:：]"), "纯视频"),
    (re.compile(r"活动征集|报名通道|诚邀参加|征集启事"), "活动通知"),
]


def _is_market_intel(title: str) -> str:
    """命中返回原因字符串,否则 ''。"""
    has_capacity = re.search(r"\d+\s*(MW|GW|GWh|MWh)", title, re.IGNORECASE)
    has_procure = re.search(r"中标|开标|采购公告|招标公告|招标|EPC|中标公示|开标公示", title)
    if has_capacity and has_procure:
        return "采购招标+容量"
    if re.search(r"采购公告|招标公告|中标公示|开标公示", title):
        return "采购招标公示"
    if re.search(r"IPO|上市|完成.{0,6}融资|融资|过会", title):
        return "资本市场动态"
    if re.search(r"出货.{0,8}(GWh|GW|万|亿)|同比增长.*%", title):
        return "出货/增速数据"
    return ""


def classify(item: FeedItem) -> Classification:
    title = item.title or ""
    for pat, reason in SKIP_PATTERNS:
        if pat.search(title):
            return Classification(Disposition.SKIP_JUNK, [reason])
    mi = _is_market_intel(title)
    if mi:
        return Classification(Disposition.MARKET_INTEL, [mi])
    return Classification(Disposition.INGEST, [])
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_filters.py -v`
Expected: PASS(8 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/commentary_ingest/filters.py tests/l1_collect/commentary_ingest/test_filters.py
git commit -m "feat(commentary-ingest): 统一结构性过滤(SKIP/market_intel)"
```

---

## Task 5: 写入(vault commentary + market_intel staging)

**Files:**
- Create: `scripts/l1_collect/commentary_ingest/writer.py`
- Test: `tests/l1_collect/commentary_ingest/test_writer.py`

- [ ] **Step 1: 写测试**

`tests/l1_collect/commentary_ingest/test_writer.py`:

```python
from pathlib import Path

import yaml

from scripts.l1_collect.commentary_ingest.models import FeedItem
from scripts.l1_collect.commentary_ingest.writer import (
    sanitize_filename, stage_market_intel, write_commentary,
)


def _item(title="测试评论标题"):
    return FeedItem(id="b" * 22,
                    url="https://mp.weixin.qq.com/s/" + "b" * 22,
                    title=title, content_html="x",
                    date_published="2026-04-28", source_account="某能源号")


def _read_fm(path: Path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fm_text = text.split("---\n", 2)[1]
    return yaml.safe_load(fm_text), text


def test_write_commentary_creates_schema_compliant_file(tmp_path):
    path = write_commentary(_item(), "正文内容若干。", tmp_path)
    assert path.exists()
    fm, text = _read_fm(path)
    assert fm["title"] == "测试评论标题"
    assert fm["source_account"] == "某能源号"
    assert fm["source_url"].endswith("b" * 22)
    assert fm["date_published"] == "2026-04-28"
    assert fm["source"] == "wewe-rss"
    assert "fetched_at" in fm
    # L1 纪律:不写 LLM 判定字段
    assert "commentary_type" not in fm
    assert "business_tag" not in fm
    assert "related_policy" not in fm
    # 正文带标题
    assert "# 测试评论标题" in text
    assert "正文内容若干。" in text


def test_write_commentary_only_required_field_is_title(tmp_path):
    # schema commentary 仅 title 必填;其余字段都在白名单内
    allowed = {"title", "source_account", "source_url", "date_published",
               "fetched_at", "source"}
    fm, _ = _read_fm(write_commentary(_item(), "正文。", tmp_path))
    assert set(fm.keys()) <= allowed
    assert "title" in fm


def test_write_commentary_collision_appends_suffix(tmp_path):
    p1 = write_commentary(_item("同名"), "正文一。", tmp_path)
    p2 = write_commentary(_item("同名"), "正文二。", tmp_path)
    assert p1 != p2
    assert p2.stem.endswith("__1")


def test_sanitize_filename_replaces_illegal_chars():
    assert "/" not in sanitize_filename("a/b:c?d")
    assert sanitize_filename("   ") == "untitled"


def test_stage_market_intel_writes_json_not_vault(tmp_path):
    path = stage_market_intel(_item("河北200MW储能中标公示"), "正文。",
                              tmp_path, "2026-04-28", ["采购招标+容量"])
    assert path.suffix == ".json"
    assert "market_intel_staging" in str(path)
    assert "2026-04-28" in str(path)
    import json
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["id"] == "b" * 22
    assert rec["reasons"] == ["采购招标+容量"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_writer.py -v`
Expected: FAIL,`ModuleNotFoundError: ... writer`

- [ ] **Step 3: 实现 writer.py**

`scripts/l1_collect/commentary_ingest/writer.py`:

```python
"""写 vault commentary md(仅追加)+ market_intel staging json。

frontmatter 确定性,只写 SCHEMA commentary 白名单内字段,不写 LLM 判定
(commentary_type/business_tag/related_policy 留给 L2)。
文件名规则对齐现有 vault(非法字符替换 + 截断 80 + 碰撞 __n)。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .models import FeedItem

CST = timezone(timedelta(hours=8))


def sanitize_filename(title: str) -> str:
    t = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", title)[:80]
    return t.strip() or "untitled"


def write_commentary(item: FeedItem, body: str, vault_dir: Path) -> Path:
    """写 {vault_dir}/0_raw/commentaries/{title}.md,返回路径。仅追加(不覆盖)。"""
    com_dir = Path(vault_dir) / "0_raw" / "commentaries"
    com_dir.mkdir(parents=True, exist_ok=True)
    fm = {
        "title": item.title,
        "source_account": item.source_account,
        "source_url": item.url,
        "date_published": item.date_published or None,
        "fetched_at": datetime.now(CST).isoformat(timespec="seconds"),
        "source": "wewe-rss",
    }
    base = sanitize_filename(item.title)
    fn = com_dir / f"{base}.md"
    n = 1
    while fn.exists():
        fn = com_dir / f"{base}__{n}.md"
        n += 1
    body_md = f"# {item.title}\n\n{body.strip()}\n"
    content = "---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n" + body_md
    fn.write_text(content, encoding="utf-8")
    return fn


def stage_market_intel(item: FeedItem, body: str, state_dir: Path,
                       run_date: str, reasons: list) -> Path:
    """market_intel 文章暂存 json(不入 vault),等 B1。"""
    out_dir = Path(state_dir) / "commentary_ingest" / "market_intel_staging" / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = {
        "id": item.id,
        "url": item.url,
        "title": item.title,
        "source_account": item.source_account,
        "date_published": item.date_published,
        "body": body,
        "reasons": reasons,
        "staged_at": datetime.now(CST).isoformat(timespec="seconds"),
    }
    path = out_dir / f"{item.id}.json"
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_writer.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/commentary_ingest/writer.py tests/l1_collect/commentary_ingest/test_writer.py
git commit -m "feat(commentary-ingest): vault 写入 + market_intel 暂存"
```

---

## Task 6: 去重台账 + last_run

**Files:**
- Create: `scripts/l1_collect/commentary_ingest/ledger.py`
- Test: `tests/l1_collect/commentary_ingest/test_ledger.py`

- [ ] **Step 1: 写测试**

`tests/l1_collect/commentary_ingest/test_ledger.py`:

```python
import json
from pathlib import Path

from scripts.l1_collect.commentary_ingest.ledger import (
    load_seen_urls, record_dispositions, write_last_run,
)


def test_load_seen_urls_reads_vault_frontmatter(tmp_path):
    com = tmp_path / "vault" / "0_raw" / "commentaries"
    com.mkdir(parents=True)
    (com / "a.md").write_text(
        "---\ntitle: A\nsource_url: https://mp.weixin.qq.com/s/" + "a" * 22
        + "\nsource: wewe-rss\n---\n\n# A\n正文\n", encoding="utf-8")
    seen = load_seen_urls(tmp_path / "vault", tmp_path / "state")
    assert "https://mp.weixin.qq.com/s/" + "a" * 22 in seen


def test_load_seen_urls_includes_ledger(tmp_path):
    state = tmp_path / "state" / "commentary_ingest"
    state.mkdir(parents=True)
    (state / "processed_ids.jsonl").write_text(
        json.dumps({"id": "x", "url": "https://mp.weixin.qq.com/s/" + "c" * 22,
                    "disposition": "skip_junk"}) + "\n", encoding="utf-8")
    seen = load_seen_urls(tmp_path / "vault", tmp_path / "state")
    assert "https://mp.weixin.qq.com/s/" + "c" * 22 in seen


def test_record_dispositions_appends_jsonl(tmp_path):
    record_dispositions(tmp_path / "state", [
        {"id": "1", "url": "u1", "disposition": "ingest", "reasons": []},
    ])
    record_dispositions(tmp_path / "state", [
        {"id": "2", "url": "u2", "disposition": "skip_junk", "reasons": ["招聘"]},
    ])
    lines = (tmp_path / "state" / "commentary_ingest" / "processed_ids.jsonl"
             ).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_write_last_run_writes_summary(tmp_path):
    write_last_run(tmp_path / "state", {"ingested": 3, "token_status": "valid"})
    rec = json.loads((tmp_path / "state" / "commentary_ingest" / "last_run.json"
                      ).read_text(encoding="utf-8"))
    assert rec["ingested"] == 3
    assert "ran_at" in rec
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_ledger.py -v`
Expected: FAIL,`ModuleNotFoundError: ... ledger`

- [ ] **Step 3: 实现 ledger.py**

`scripts/l1_collect/commentary_ingest/ledger.py`:

```python
"""去重台账:已见 source_url 集合(vault 现有 + 历史 ledger)+ 处置记录 + last_run。

去重主键 = source_url。vault 现有 283 篇预先存在(早于本 ledger),故每轮都
扫 vault commentary frontmatter 取 source_url,叠加 ledger,保证幂等。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
_SRC_URL_RE = re.compile(r"^source_url:\s*(\S+)\s*$", re.MULTILINE)


def load_seen_urls(vault_dir: Path, state_dir: Path) -> set:
    seen = set()
    com_dir = Path(vault_dir) / "0_raw" / "commentaries"
    if com_dir.exists():
        for f in com_dir.glob("*.md"):
            m = _SRC_URL_RE.search(f.read_text(encoding="utf-8", errors="ignore"))
            if m:
                seen.add(m.group(1))
    ledger = Path(state_dir) / "commentary_ingest" / "processed_ids.jsonl"
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                url = json.loads(line).get("url")
            except json.JSONDecodeError:
                continue
            if url:
                seen.add(url)
    return seen


def record_dispositions(state_dir: Path, entries: list) -> None:
    out = Path(state_dir) / "commentary_ingest"
    out.mkdir(parents=True, exist_ok=True)
    ledger = out / "processed_ids.jsonl"
    ts = datetime.now(CST).isoformat(timespec="seconds")
    with ledger.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps({**e, "ts": ts}, ensure_ascii=False) + "\n")


def write_last_run(state_dir: Path, summary: dict) -> None:
    out = Path(state_dir) / "commentary_ingest"
    out.mkdir(parents=True, exist_ok=True)
    rec = {"ran_at": datetime.now(CST).isoformat(timespec="seconds"), **summary}
    (out / "last_run.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_ledger.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/commentary_ingest/ledger.py tests/l1_collect/commentary_ingest/test_ledger.py
git commit -m "feat(commentary-ingest): 去重台账 + last_run"
```

---

## Task 7: token 健康检查 + 告警

**Files:**
- Create: `scripts/l1_collect/commentary_ingest/token_health.py`
- Test: `tests/l1_collect/commentary_ingest/test_token_health.py`

- [ ] **Step 1: 写测试**(用临时 sqlite 造 accounts 表)

`tests/l1_collect/commentary_ingest/test_token_health.py`:

```python
import sqlite3
from pathlib import Path

from scripts.l1_collect.commentary_ingest.token_health import check_token


def _make_db(tmp_path: Path, status: int) -> Path:
    db = tmp_path / "wewe-rss.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE accounts (id TEXT, name TEXT, status INTEGER, "
                "token TEXT, updated_at TEXT)")
    con.execute("INSERT INTO accounts VALUES ('1','邵子渊',?,'tok','2026-04-29')",
                (status,))
    con.commit()
    con.close()
    return db


def test_check_token_valid_when_status_1(tmp_path):
    st = check_token(_make_db(tmp_path, 1))
    assert st.valid is True


def test_check_token_invalid_when_status_0(tmp_path):
    st = check_token(_make_db(tmp_path, 0))
    assert st.valid is False
    assert st.account_name == "邵子渊"


def test_check_token_invalid_when_db_missing(tmp_path):
    st = check_token(tmp_path / "nope.db")
    assert st.valid is False
    assert "无法读取" in st.detail
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_token_health.py -v`
Expected: FAIL,`ModuleNotFoundError: ... token_health`

- [ ] **Step 3: 实现 token_health.py**

`scripts/l1_collect/commentary_ingest/token_health.py`:

```python
"""检测 wewe-rss 微信 token 是否失效 + 告警。

判据:读 sqlite accounts.status(1=有效, 0=失效)。任一账号失效即需重新扫码。
告警通道:ALERT_WEBHOOK_URL(POST json)优先,无则仅记日志返回。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class TokenStatus:
    valid: bool
    account_name: str = ""
    detail: str = ""


def check_token(db_path: Path) -> TokenStatus:
    db_path = Path(db_path)
    if not db_path.exists():
        return TokenStatus(False, "", f"无法读取 wewe-rss DB: {db_path}")
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = con.execute("SELECT name, status FROM accounts").fetchall()
        con.close()
    except sqlite3.Error as e:
        return TokenStatus(False, "", f"无法读取 accounts: {e}")
    if not rows:
        return TokenStatus(False, "", "accounts 表为空,未登录")
    invalid = [name for name, status in rows if status != 1]
    if invalid:
        return TokenStatus(False, invalid[0],
                           f"{len(invalid)} 个账号 token 失效,需重新扫码")
    return TokenStatus(True, rows[0][0], "token 有效")


def alert(message: str, webhook_url: str = "") -> bool:
    """发告警。有 webhook 则 POST,返回是否送达;无则返回 False(调用方记日志)。"""
    if not webhook_url:
        return False
    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=15)
        return resp.ok
    except Exception:
        return False
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_token_health.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/commentary_ingest/token_health.py tests/l1_collect/commentary_ingest/test_token_health.py
git commit -m "feat(commentary-ingest): token 失效检测 + 告警"
```

---

## Task 8: CLI 编排 run.py

**Files:**
- Create: `scripts/l1_collect/commentary_ingest/run.py`
- Test: `tests/l1_collect/commentary_ingest/test_run.py`

- [ ] **Step 1: 写测试**(注入假 feed,验证端到端处置 + 幂等)

`tests/l1_collect/commentary_ingest/test_run.py`:

```python
import json
from pathlib import Path

from scripts.l1_collect.commentary_ingest.models import FeedItem
from scripts.l1_collect.commentary_ingest.run import ingest_items


def _items():
    return [
        FeedItem("a" * 22, "https://mp.weixin.qq.com/s/" + "a" * 22,
                 "IIGF观点 | 制度比较与中国路径", "<p>" + "正文。" * 80 + "</p>",
                 "2026-04-28", "中央财经大学绿色金融国际研究院"),
        FeedItem("b" * 22, "https://mp.weixin.qq.com/s/" + "b" * 22,
                 "河北200MW800MWh储能项目EPC中标公示", "<p>" + "行情。" * 80 + "</p>",
                 "2026-04-27", "储能与电力市场"),
        FeedItem("c" * 22, "https://mp.weixin.qq.com/s/" + "c" * 22,
                 "诚聘英才|2026校园招聘", "<p>" + "招聘。" * 80 + "</p>",
                 "2026-04-26", "某号"),
    ]


def test_ingest_items_routes_by_disposition(tmp_path):
    vault, state = tmp_path / "vault", tmp_path / "state"
    summary = ingest_items(_items(), vault_dir=vault, state_dir=state,
                           fetch_fallback=False)
    assert summary["ingested"] == 1
    assert summary["market_intel"] == 1
    assert summary["skipped_junk"] == 1
    # commentary 落了 1 篇
    assert len(list((vault / "0_raw" / "commentaries").glob("*.md"))) == 1
    # market_intel 暂存 1 条
    staged = list((state / "commentary_ingest" / "market_intel_staging").rglob("*.json"))
    assert len(staged) == 1


def test_ingest_items_idempotent_second_run_skips_all(tmp_path):
    vault, state = tmp_path / "vault", tmp_path / "state"
    ingest_items(_items(), vault_dir=vault, state_dir=state, fetch_fallback=False)
    summary2 = ingest_items(_items(), vault_dir=vault, state_dir=state,
                            fetch_fallback=False)
    assert summary2["duplicates"] == 3
    assert summary2["ingested"] == 0
    # 没多写文件
    assert len(list((vault / "0_raw" / "commentaries").glob("*.md"))) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_run.py -v`
Expected: FAIL,`ModuleNotFoundError: ... run`

- [ ] **Step 3: 实现 run.py**

`scripts/l1_collect/commentary_ingest/run.py`:

```python
"""commentary_ingest 编排 CLI。

用法:
  python3 -m scripts.l1_collect.commentary_ingest.run \\
    --feed-url http://localhost:4000/feeds/all.json \\
    --auth-code "$WEWE_AUTH_CODE" \\
    --vault-dir "$VAULT_DIR" --state-dir state \\
    --db-path ~/wewe-rss-data/wewe-rss.db

  # 仅检查 token:
  python3 -m scripts.l1_collect.commentary_ingest.run --check-token \\
    --db-path ~/wewe-rss-data/wewe-rss.db

所有路径/凭据经 CLI/env 注入,零硬编码(可移植 spec §9)。
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .content import to_body
from .feed_client import fetch_feed
from .filters import classify
from .ledger import load_seen_urls, record_dispositions, write_last_run
from .models import Disposition, FeedItem
from .token_health import alert, check_token
from .writer import stage_market_intel, write_commentary

CST = timezone(timedelta(hours=8))


def ingest_items(items: list, *, vault_dir: Path, state_dir: Path,
                 fetch_fallback: bool = True) -> dict:
    """对一批 FeedItem 执行 去重→过滤→正文→写入→记账,返回 summary。"""
    seen = load_seen_urls(vault_dir, state_dir)
    run_date = datetime.now(CST).strftime("%Y-%m-%d")
    summary = {"feed_count": len(items), "ingested": 0, "market_intel": 0,
               "skipped_junk": 0, "duplicates": 0, "unprocessable": 0}
    entries = []
    for item in items:
        if not item.id or len(item.id) != 22:
            summary["unprocessable"] += 1
            entries.append({"id": item.id, "url": item.url,
                            "disposition": "unprocessable", "reasons": ["bad_id"]})
            continue
        if item.url in seen:
            summary["duplicates"] += 1
            continue
        seen.add(item.url)
        cls = classify(item)
        if cls.disposition == Disposition.SKIP_JUNK:
            summary["skipped_junk"] += 1
            entries.append({"id": item.id, "url": item.url,
                            "disposition": "skip_junk", "reasons": cls.reasons})
            continue
        body, src = to_body(item, fetch_fallback=fetch_fallback)
        if src == "empty":
            summary["unprocessable"] += 1
            entries.append({"id": item.id, "url": item.url,
                            "disposition": "unprocessable", "reasons": ["no_body"]})
            continue
        if cls.disposition == Disposition.MARKET_INTEL:
            stage_market_intel(item, body, state_dir, run_date, cls.reasons)
            summary["market_intel"] += 1
            entries.append({"id": item.id, "url": item.url,
                            "disposition": "market_intel", "reasons": cls.reasons})
            continue
        path = write_commentary(item, body, vault_dir)
        summary["ingested"] += 1
        entries.append({"id": item.id, "url": item.url, "disposition": "ingest",
                        "reasons": [], "file": path.name, "body_src": src})
    record_dispositions(state_dir, entries)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="commentary RSS 入库")
    ap.add_argument("--feed-url", default=os.environ.get("WEWE_FEED_URL", ""))
    ap.add_argument("--auth-code", default=os.environ.get("WEWE_AUTH_CODE", ""))
    ap.add_argument("--vault-dir", default=os.environ.get("VAULT_DIR", ""))
    ap.add_argument("--state-dir", default=os.environ.get("STATE_DIR", "state"))
    ap.add_argument("--db-path", default=os.environ.get("WEWE_DB_PATH", ""))
    ap.add_argument("--alert-webhook", default=os.environ.get("ALERT_WEBHOOK_URL", ""))
    ap.add_argument("--check-token", action="store_true")
    ap.add_argument("--no-fallback", action="store_true",
                    help="不做正文兜底抓取(只用 feed 全文)")
    args = ap.parse_args()

    # token 健康检查(--check-token 或每轮入库前都查一次)
    if args.db_path:
        st = check_token(Path(args.db_path))
        if not st.valid:
            msg = f"[commentary-ingest] wewe-rss token 失效:{st.detail}（账号 {st.account_name}）需重新扫码"
            if not alert(msg, args.alert_webhook):
                print(msg)
        if args.check_token:
            print(f"token valid={st.valid} detail={st.detail}")
            return 0 if st.valid else 1

    if not args.feed_url or not args.vault_dir:
        ap.error("缺 --feed-url / --vault-dir(或对应 env)")
    items = fetch_feed(args.feed_url, args.auth_code)
    summary = ingest_items(items, vault_dir=Path(args.vault_dir),
                           state_dir=Path(args.state_dir),
                           fetch_fallback=not args.no_fallback)
    token_status = "valid"
    if args.db_path:
        token_status = "valid" if check_token(Path(args.db_path)).valid else "invalid"
    write_last_run(Path(args.state_dir), {**summary, "token_status": token_status})
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/test_run.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: 全包测试 + 提交**

```bash
python3 -m pytest tests/l1_collect/commentary_ingest/ -v
git add scripts/l1_collect/commentary_ingest/run.py tests/l1_collect/commentary_ingest/test_run.py
git commit -m "feat(commentary-ingest): CLI 编排 + 端到端入库/幂等"
```

---

## Task 9: 端到端真跑 + schema gate(集成验证)

**Files:**
- (无新代码;验证 + 记录)
- Create: `state/commentary_ingest/.gitignore`(放行 last_run/ledger,挡 staging 正文)

- [ ] **Step 1: state 子目录 gitignore(挡正文,放行台账)**

`state/commentary_ingest/.gitignore`:

```
*
!.gitignore
!.gitkeep
!processed_ids.jsonl
!last_run.json
```

- [ ] **Step 2: 对真实 wewe-rss 干跑(写临时 vault,不污染真 vault)**

> 复用 Task 1 启动的 wewe-rss 容器。先小批量 `--no-fallback` 验证 feed 全文够用。

Run:
```bash
mkdir -p /tmp/ci_vault
python3 -m scripts.l1_collect.commentary_ingest.run \
  --feed-url 'http://localhost:4000/feeds/all.json?limit=30' \
  --auth-code zayn-policy-2026 \
  --vault-dir /tmp/ci_vault --state-dir /tmp/ci_state \
  --db-path ~/wewe-rss-data/wewe-rss.db --no-fallback
ls /tmp/ci_vault/0_raw/commentaries/ | head
cat /tmp/ci_state/commentary_ingest/last_run.json
```

Expected:summary 打印各处置计数;`/tmp/ci_vault/0_raw/commentaries/` 有 md;`last_run.json` 含 `token_status: invalid`(当前 token 失效);若 `unprocessable` 偏高说明 feed 全文不足 → 去掉 `--no-fallback` 重试。

- [ ] **Step 3: 过 schema 校验**

Run:
```bash
python3 scripts/audit/validate_schema.py --vault /tmp/ci_vault 2>/dev/null || \
python3 -c "
from pathlib import Path
from scripts.audit.validate_schema import check_commentary
bad=[]
for f in Path('/tmp/ci_vault/0_raw/commentaries').glob('*.md'):
    v,_=check_commentary(f)
    bad+=v
print('violations:', bad)
assert not bad, bad
print('schema OK')
"
```

Expected:`schema OK`,无 violations(印证 spec §12.6:6 字段全白名单、仅 title 必填)。

- [ ] **Step 4: 验证 token 失效告警路径**

Run:
```bash
python3 -m scripts.l1_collect.commentary_ingest.run --check-token \
  --db-path ~/wewe-rss-data/wewe-rss.db; echo "exit=$?"
```

Expected:打印 `token valid=False ...`,`exit=1`,并打印失效告警文案(无 webhook 时走 stdout)。

- [ ] **Step 5: 清理临时产物 + 提交 gitignore**

```bash
rm -rf /tmp/ci_vault /tmp/ci_state
git add state/commentary_ingest/.gitignore
git commit -m "chore(commentary-ingest): state 子目录 gitignore(挡正文放行台账)"
```

---

## Task 10: wewe-rss 容器定义(阶段二迁移目标)

**Files:**
- Create: `docker/wewe-rss/compose.yml`

- [ ] **Step 1: 写 compose**(国内容器节点用;Mac 阶段一可继续用 `docker run`)

`docker/wewe-rss/compose.yml`:

```yaml
# wewe-rss + commentary-ingest 国内容器节点部署(阶段二)
# 凭据经 .env 注入(AUTH_CODE / ALERT_WEBHOOK_URL),.env 不入 git。
# 阶段一(Mac)可不用本文件,直接 docker run wewe-rss + cron 跑 ingest。
services:
  wewe-rss:
    image: cooderl/wewe-rss-sqlite:latest
    container_name: wewe-rss
    restart: unless-stopped
    ports:
      - "4000:4000"          # QR 扫码管理页 + feed;按需收敛到内网/反代
    environment:
      DATABASE_TYPE: sqlite
      AUTH_CODE: ${WEWE_AUTH_CODE}
      SERVER_ORIGIN_URL: http://localhost:4000
      FEED_MODE: fulltext
      ENABLE_CLEAN_HTML: "true"
      # 保守轮询(spec §6.2):每 6 小时一次,降低 token 失效与封号风险
      CRON_EXPRESSION: "0 0 */6 * * *"
    volumes:
      - ./data:/app/data     # SQLite + token;映射到国内节点持久盘
```

> ingest 本身是 Python 进程(cron / 容器内 entrypoint),按节点情况接入;迁移文档(Task 11)给两种接法。`CRON_EXPRESSION` 取值以实际 wewe-rss 版本支持的格式为准,迁移时验证一次。

- [ ] **Step 2: 提交**

```bash
git add docker/wewe-rss/compose.yml
git commit -m "feat(commentary-ingest): wewe-rss 容器定义(阶段二迁移目标)"
```

---

## Task 11: 迁移文档 + CLAUDE.md 摘要

**Files:**
- Create: `docs/runbooks/commentary-rss-ingest-migration.md`
- Modify: `CLAUDE.md`(项目根,追加一节)

- [ ] **Step 1: 写迁移 runbook**

`docs/runbooks/commentary-rss-ingest-migration.md`(完整内容):

```markdown
# 评论 RSS 入库 · Mac→国内容器 迁移 runbook

## 现状(阶段一,Mac)
- wewe-rss:`docker run ... cooderl/wewe-rss-sqlite:latest`(端口 4000,数据卷 ~/wewe-rss-data)
- ingest:`python3 -m scripts.l1_collect.commentary_ingest.run`,Mac cron 定时
- 写 Mac vault 0_raw/commentaries/,经现有 Mac→东京 rsync 上服务器只读消费

## 为什么国内(不上东京服务器)
token 是个人微信读书账号;东京机房 IP 触发微信地理风控(最坏冻结账号)。详见 spec §6.1。
**国内容器节点同理:token 必须从国内 IP 发起。**

## 迁移步骤(定下国内容器节点后)
1. 国内节点装 Docker;`docker/wewe-rss/compose.yml` 起 wewe-rss,挂持久盘。
2. 把 Mac 的 `~/wewe-rss-data/wewe-rss.db` scp 到节点 `./data/`(保留已登录 token,免重扫)。
   - 若 token 已失效:开 4000 管理页,手机微信扫码重登(见"扫码")。
3. 配 `.env`:`WEWE_AUTH_CODE` / `ALERT_WEBHOOK_URL`(不入 git)。
4. ingest 接入(二选一):
   - a) 节点 cron:`cd <repo> && VAULT_DIR=<vault> WEWE_FEED_URL=http://wewe-rss:4000/feeds/all.json WEWE_AUTH_CODE=... python3 -m scripts.l1_collect.commentary_ingest.run --db-path <db>`
   - b) ingest 也容器化,与 wewe-rss 同 compose 网络,feed-url 用服务名 `http://wewe-rss:4000/...`
5. vault 落地与回流:节点写本地 vault 副本 → 约定回流路径(rsync 回 Mac 或直接作为新的 vault 著作点,二选一,迁移时定并更新 spec §9 + 本 runbook)。
6. 验证:`--check-token` 通;小批量 `--no-fallback` 干跑;过 `validate_schema`。

## 扫码(token 失效时)
1. 浏览器开节点 `http://<节点>:4000`(或反代),输入 AUTH_CODE 进管理页。
2. 账号管理 → 扫码登录 → 手机微信扫 → token 刷新。
3. （后续)openclaw + IM 模块:自动把 QR 推到 IM,远程扫——独立 spec,届时接 `--check-token` 告警为触发点。

## 保守轮询纪律
轮询越勤 → token 废越快 → 扫码越频繁(且抬高封号风险)。`CRON_EXPRESSION` 维持 6h/次量级,勿调激进。
```

- [ ] **Step 2: CLAUDE.md 追加迁移摘要**

在项目根 `CLAUDE.md` 的"关键运行入口"章节后追加:

```markdown
## 评论 RSS 入库(L1 commentary)

评论采集 = wewe-rss(微信公众号→JSON feed)→ `scripts/l1_collect/commentary_ingest/`。

**部署纪律(重要)**:token 是个人微信读书账号,**必须从国内 IP 发起**——东京服务器机房 IP 会触发微信地理风控(最坏冻结账号)。故此线跑**国内节点**(阶段一 Mac,阶段二国内容器),写 Mac vault 经现有 rsync 上服务器只读消费,**不在东京服务器跑 discovery、不写 /root/policy-vault**。

- 运行:`python3 -m scripts.l1_collect.commentary_ingest.run --feed-url ... --vault-dir ... --db-path ...`(路径/凭据全 env/CLI,零硬编码)
- 迁移:`docs/runbooks/commentary-rss-ingest-migration.md`(方法更新时同步维护本节与该 runbook)
- 保守轮询:轮询越勤→token 废越快→扫码越频繁。CRON 维持 6h/次量级。
```

- [ ] **Step 3: 跑全量测试确认无回归**

Run: `python3 -m pytest tests/l1_collect/commentary_ingest/ -v`
Expected: 全 PASS

- [ ] **Step 4: 提交**

```bash
git add docs/runbooks/commentary-rss-ingest-migration.md CLAUDE.md
git commit -m "docs(commentary-ingest): 迁移 runbook + CLAUDE.md 部署纪律摘要"
```

---

## 收尾

- [ ] 全包测试通过:`python3 -m pytest tests/l1_collect/commentary_ingest/ -v`
- [ ] 凭据零泄漏自查:`git grep -i "zayn-policy-2026\|token\|wr_skey" -- scripts/ docs/ docker/`(应只在 runbook 注释/占位,无真 token)
- [ ] 主 session 须知已就位:`docs/handoffs/2026-06-07-commentary-ingest-handoff.md`
- [ ] 用户扫码刷新 token 后,跑一次有效态真入库验证(本计划范围内的最后人工步)
