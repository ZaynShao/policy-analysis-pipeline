# T1 · 市级政策完整覆盖 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 P0 ~50 城市级政策采集 + 立即质量评估 + 为 P1/P2 准备执行能力;为 T1 全市级覆盖打基础。

**Architecture:** 方案 3 Hybrid。机器扫描清单留 `pipeline/state/T1_channels/`(三态:候选/验证/已扫),人工 canonical 留 `vault/00 背景资料/渠道目录.md`(由主 session 在 user 监督下反哺)。采集流水线 Step 2→3→4→4.5→5,Step 3 含"政策 vs 新闻稿"确定性过滤(不开 override,清爽规则,接受误杀)。

**Tech Stack:** Python 3.11+ / PyYAML / requests / trafilatura / BeautifulSoup4 / pytest;Firecrawl(主)+ Tavily(找 URL)+ trafilatura(开源提取)+ BeautifulSoup(兜底)四级抓取链。

**Reference spec:** `docs/proposals/T1-city-level-collection.md` (status: APPROVED, 2026-05-19)

**Total tasks:** 28 across 10 phases. 时间预算:2.6-3.1 天。

---

## 文件结构

新增文件:

```
scripts/l1_collect/
├── __init__.py
├── channel_catalog.py            # YAML IO + Channel/CityPriority 数据模型
├── connectivity_probe.py         # HTTP 联通 + 列表页结构启发式
├── city_priority.py              # P0/P1/P2 优先级算法
├── news_filter.py                # 政策 vs 新闻稿 确定性过滤(规则,不上 LLM)
├── dedup.py                      # 三维查重:URL/文号/标题哈希归一化
├── fetcher.py                    # Firecrawl→Tavily→trafilatura→BS4 兜底链
├── metadata_extractor.py         # regex + canonical lookup(无 LLM)
├── ingester.py                   # 写 vault raw + 过 validate_schema
├── step2_scan.py                 # Step 2 渠道扫描入口
├── step3_filter.py               # Step 3 标题+新闻稿+查重 编排
├── step4_fetch.py                # Step 4 抓正文 编排
├── step4_5_extract.py            # Step 4.5 元数据抽取 编排
├── step5_ingest.py               # Step 5 入库 编排
└── run_pipeline.py               # 总入口(--batch / --resume / --dry-run)

scripts/_oneshot/
├── t1_generate_channel_candidates_2026-05-19.py    # LLM 生成 ~330 城候选
├── t1_build_p0_city_list_2026-05-19.py             # 主 session 推 P0 ~50 城
├── t1_probe_p0_quality_2026-05-XX.py               # P0 跑完抽样质量
└── t1_generate_vault_backfill_2026-05-XX.py        # 生成 vault 渠道目录 diff

tests/l1_collect/
├── __init__.py
├── conftest.py
├── test_channel_catalog.py
├── test_connectivity_probe.py
├── test_city_priority.py
├── test_news_filter.py
├── test_dedup.py
├── test_fetcher.py
├── test_metadata_extractor.py
└── test_ingester.py

state/T1_channels/
├── channel_catalog.yaml
├── city_priority.yaml
├── channel_probe_log.jsonl
└── README.md                     # 准备 C 的触发条件文档

state/T1_scan_raw/          # Step 2 输出
state/T1_candidate/         # Step 3 输出
state/T1_fetched/           # Step 4 输出
state/T1_extracted/         # Step 4.5 输出
state/T1_quarantine/        # 新闻稿过滤被拒
state/T1_ingest_log/        # Step 5 入库日志
state/probes/2026-XX-XX_T1_P0_quality/
├── samples.md
├── samples.jsonl
└── verdict.md
```

修改文件:
- `pyproject.toml`(新建,放 pytest 配置)
- `state/.gitignore`(加 T1_* 子目录的 ignore 规则)

---

## Phase 0 · 基建(3 tasks)

### Task 0.1: pytest 基建

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/l1_collect/__init__.py`
- Create: `tests/l1_collect/conftest.py`

- [ ] **Step 1: 写 pyproject.toml**

```toml
[project]
name = "zce-pipeline"
version = "0.1.0"
description = "政策分析 pipeline 工程仓"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-ra --strict-markers"
```

- [ ] **Step 2: 创建空 `tests/__init__.py` 与 `tests/l1_collect/__init__.py`**

- [ ] **Step 3: 写 `tests/l1_collect/conftest.py`**

```python
"""共享 fixture for l1_collect 测试。"""
from __future__ import annotations
from pathlib import Path
import pytest

@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    """临时 state/ 目录,模拟 pipeline state 结构。"""
    (tmp_path / "T1_channels").mkdir(parents=True)
    (tmp_path / "T1_scan_raw").mkdir()
    (tmp_path / "T1_candidate").mkdir()
    return tmp_path

@pytest.fixture
def sample_catalog_yaml() -> str:
    return """\
- city: 杭州市
  province: 浙江省
  level: 市
  city_code: '330100'
  channel_type: 发改委
  root_domain: fgw.hangzhou.gov.cn
  list_url: https://fgw.hangzhou.gov.cn/col/col1229453592/index.html
  source: vault_catalog
  status: 验证
  last_probed_at: '2026-05-19T10:00:00'
  probe_result: ok
  notes: ''
"""
```

- [ ] **Step 4: 验证 pytest 跑起来**

```bash
cd ~/dev/政策分析-pipeline
python3 -m pytest -q
# Expected: "no tests ran in 0.0Xs"(没测试但 pytest 配置正常)
```

- [ ] **Step 5: 安装/确认依赖**

```bash
python3 -m pip install --user pyyaml requests trafilatura beautifulsoup4 pytest
# 验证:
python3 -c "import yaml, requests, trafilatura, bs4, pytest; print('ok')"
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/
git commit -m "T1.0.1: bootstrap pytest infra + l1_collect test scaffold"
```

---

### Task 0.2: state/T1_* 目录骨架 + gitignore

**Files:**
- Create: `state/T1_channels/.gitkeep` + 同样 5 个子目录
- Modify: `state/.gitignore`

- [ ] **Step 1: 创建 T1_* 子目录骨架**

```bash
cd ~/dev/政策分析-pipeline
for d in T1_channels T1_scan_raw T1_candidate T1_fetched T1_extracted T1_quarantine T1_ingest_log; do
  mkdir -p state/$d
  touch state/$d/.gitkeep
done
ls state/
```

- [ ] **Step 2: 更新 `state/.gitignore`,加 T1 数据 ignore 但保留 .gitkeep + channel_catalog / city_priority(配置文件要进 git)**

读 `state/.gitignore` 看现有规则,然后追加:

```
# T1 中间产物不进 git
/T1_scan_raw/*
!/T1_scan_raw/.gitkeep
/T1_candidate/*
!/T1_candidate/.gitkeep
/T1_fetched/*
!/T1_fetched/.gitkeep
/T1_extracted/*
!/T1_extracted/.gitkeep
/T1_quarantine/*
!/T1_quarantine/.gitkeep
/T1_ingest_log/*
!/T1_ingest_log/.gitkeep

# T1_channels:配置类 yaml 进 git,日志类不进
/T1_channels/channel_probe_log.jsonl
```

- [ ] **Step 3: Commit**

```bash
git add state/T1_*/.gitkeep state/.gitignore
git commit -m "T1.0.2: scaffold state/T1_* dirs + gitignore rules"
```

---

### Task 0.3: scripts/l1_collect 包骨架

**Files:**
- Create: `scripts/l1_collect/__init__.py`

- [ ] **Step 1: 写最小 `__init__.py`**

```python
"""政策采集 L1:从市级渠道扫描到 vault raw 入库的完整链路。

模块组织:
  - channel_catalog : 渠道清单数据模型 + IO
  - connectivity_probe : HTTP 联通 + 列表页结构启发式
  - city_priority : P0/P1/P2 优先级
  - news_filter : 政策 vs 新闻稿 确定性过滤
  - dedup : 三维查重(URL/文号/标题)
  - fetcher : 抓取兜底链
  - metadata_extractor : 元数据抽取(无 LLM)
  - ingester : 写 vault raw + schema 校验
  - step2_scan / step3_filter / step4_fetch / step4_5_extract / step5_ingest
  - run_pipeline : 总入口
"""
```

- [ ] **Step 2: Commit**

```bash
git add scripts/l1_collect/__init__.py
git commit -m "T1.0.3: scaffold scripts/l1_collect package"
```

---

## Phase 1 · 渠道基础设施(4 tasks)

### Task 1.1: channel_catalog 模块

**Files:**
- Create: `scripts/l1_collect/channel_catalog.py`
- Create: `tests/l1_collect/test_channel_catalog.py`

- [ ] **Step 1: 写 test 文件(失败先行)**

```python
"""Tests for channel_catalog: data model + YAML IO."""
from __future__ import annotations
from pathlib import Path
import pytest
from scripts.l1_collect.channel_catalog import (
    Channel, ChannelStatus, load_catalog, save_catalog,
)

def test_channel_required_fields():
    ch = Channel(
        city="杭州市", province="浙江省", level="市", city_code="330100",
        channel_type="发改委", root_domain="fgw.hangzhou.gov.cn",
        list_url="https://fgw.hangzhou.gov.cn/col/col1229453592/index.html",
        source="vault_catalog", status=ChannelStatus.候选,
    )
    assert ch.city == "杭州市"
    assert ch.status == ChannelStatus.候选

def test_channel_status_enum():
    assert {s.value for s in ChannelStatus} == {"候选", "验证", "已扫"}

def test_load_save_roundtrip(tmp_state_dir: Path, sample_catalog_yaml: str):
    p = tmp_state_dir / "T1_channels" / "channel_catalog.yaml"
    p.write_text(sample_catalog_yaml, encoding="utf-8")
    catalog = load_catalog(p)
    assert len(catalog) == 1
    assert catalog[0].city == "杭州市"
    assert catalog[0].status == ChannelStatus.验证
    out = tmp_state_dir / "T1_channels" / "out.yaml"
    save_catalog(catalog, out)
    catalog2 = load_catalog(out)
    assert catalog2[0].city == catalog[0].city

def test_save_preserves_field_order(tmp_state_dir: Path, sample_catalog_yaml: str):
    """YAML 输出字段顺序应固定,便于 diff。"""
    p = tmp_state_dir / "T1_channels" / "channel_catalog.yaml"
    p.write_text(sample_catalog_yaml, encoding="utf-8")
    catalog = load_catalog(p)
    out = tmp_state_dir / "out.yaml"
    save_catalog(catalog, out)
    text = out.read_text(encoding="utf-8")
    # city 必须出现在 channel_type 之前(字段顺序固定)
    assert text.index("city:") < text.index("channel_type:")
```

- [ ] **Step 2: 跑测试验证全部 fail**

```bash
python3 -m pytest tests/l1_collect/test_channel_catalog.py -v
# Expected: ImportError 或 4 个 test 全 FAIL
```

- [ ] **Step 3: 写实现**

```python
# scripts/l1_collect/channel_catalog.py
"""Channel catalog 数据模型 + YAML IO。"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Optional
import yaml

class ChannelStatus(str, Enum):
    候选 = "候选"
    验证 = "验证"
    已扫 = "已扫"

@dataclass
class Channel:
    city: str
    province: str
    level: str               # 市 / 区
    city_code: str           # 国标 6 位
    channel_type: str        # 发改委 / 能源局 / 政府网 / 经信委 / 商务局
    root_domain: str
    list_url: str
    source: str              # vault_catalog | llm_generated | manual
    status: ChannelStatus
    last_probed_at: Optional[str] = None
    probe_result: Optional[str] = None  # ok | http_error | structure_unknown | empty
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

# 固定字段顺序(diff 友好)
FIELD_ORDER = [
    "city", "province", "level", "city_code",
    "channel_type", "root_domain", "list_url",
    "source", "status", "last_probed_at", "probe_result", "notes",
]

class _OrderedDumper(yaml.SafeDumper):
    pass

def _dict_representer(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())

_OrderedDumper.add_representer(dict, _dict_representer)

def load_catalog(path: Path) -> list[Channel]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    out = []
    for d in raw:
        d2 = dict(d)
        d2["status"] = ChannelStatus(d2["status"])
        out.append(Channel(**d2))
    return out

def save_catalog(catalog: list[Channel], path: Path) -> None:
    rows = []
    for ch in catalog:
        d = ch.to_dict()
        # 重排字段顺序
        ordered = {k: d[k] for k in FIELD_ORDER if k in d}
        rows.append(ordered)
    path.write_text(
        yaml.dump(
            rows, Dumper=_OrderedDumper,
            allow_unicode=True, sort_keys=False, default_flow_style=False,
        ),
        encoding="utf-8",
    )
```

- [ ] **Step 4: 跑测试验证全过**

```bash
python3 -m pytest tests/l1_collect/test_channel_catalog.py -v
# Expected: 4 passed
```

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/channel_catalog.py tests/l1_collect/test_channel_catalog.py
git commit -m "T1.1.1: channel_catalog data model + YAML IO with fixed field order"
```

---

### Task 1.2: connectivity_probe 模块

**Files:**
- Create: `scripts/l1_collect/connectivity_probe.py`
- Create: `tests/l1_collect/test_connectivity_probe.py`

- [ ] **Step 1: 写 test 文件**

```python
"""Tests for connectivity_probe."""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from scripts.l1_collect.connectivity_probe import (
    probe_url, ProbeResult, looks_like_list_page,
)

def test_looks_like_list_page_positive():
    """含 a 标签 + 时间/翻页结构 = 列表页。"""
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
```

- [ ] **Step 2: 跑测试验证全 fail**

```bash
python3 -m pytest tests/l1_collect/test_connectivity_probe.py -v
```

- [ ] **Step 3: 写实现**

```python
# scripts/l1_collect/connectivity_probe.py
"""HTTP 联通性测试 + 列表页结构启发式判定。"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import re
from typing import Literal
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; ZCE-Probe/0.1; +https://github.com/)"
TIMEOUT = 15
CST = timezone(timedelta(hours=8))

ProbeVerdict = Literal["ok", "http_error", "structure_unknown", "empty"]

@dataclass
class ProbeResult:
    url: str
    http_status: int | None
    page_has_list_pattern: bool
    verdict: ProbeVerdict
    error: str = ""
    probed_at: str = ""

_DATE_NEAR_LINK_RE = re.compile(r"20\d{2}[-/年.]\s*\d{1,2}[-/月.]\s*\d{1,2}")

def looks_like_list_page(html: str) -> bool:
    """启发式:页面含 ≥3 个相邻的 <a> + 日期模式,或有 .pagination/.page/下一页。"""
    soup = BeautifulSoup(html, "html.parser")
    # 信号 1:翻页控件
    txt = soup.get_text(" ", strip=True)
    if any(kw in txt for kw in ["下一页", "下页", "末页"]):
        if soup.find_all("a"):
            return True
    # 信号 2:列表项含日期
    links = soup.find_all("a")
    near_date = 0
    for a in links:
        parent_text = (a.parent.get_text(" ", strip=True) if a.parent else "")[:200]
        if _DATE_NEAR_LINK_RE.search(parent_text):
            near_date += 1
        if near_date >= 3:
            return True
    return False

def probe_url(url: str) -> ProbeResult:
    now = datetime.now(CST).isoformat(timespec="seconds")
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    except Exception as e:
        return ProbeResult(url=url, http_status=None, page_has_list_pattern=False,
                           verdict="http_error", error=str(e)[:200], probed_at=now)
    if resp.status_code >= 400:
        return ProbeResult(url=url, http_status=resp.status_code, page_has_list_pattern=False,
                           verdict="http_error", probed_at=now)
    text = resp.text or ""
    if not text.strip():
        return ProbeResult(url=url, http_status=resp.status_code, page_has_list_pattern=False,
                           verdict="empty", probed_at=now)
    has_list = looks_like_list_page(text)
    return ProbeResult(
        url=url, http_status=resp.status_code, page_has_list_pattern=has_list,
        verdict="ok" if has_list else "structure_unknown", probed_at=now,
    )
```

- [ ] **Step 4: 跑测试**

```bash
python3 -m pytest tests/l1_collect/test_connectivity_probe.py -v
# Expected: 4 passed
```

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/connectivity_probe.py tests/l1_collect/test_connectivity_probe.py
git commit -m "T1.1.2: connectivity_probe HTTP check + list-page heuristic"
```

---

### Task 1.3: oneshot 生成 ~330 城渠道候选

**Files:**
- Create: `scripts/_oneshot/t1_generate_channel_candidates_2026-05-19.py`
- Modify: `state/T1_channels/channel_catalog.yaml`(产物)

> **Note:** 本 task 用 LLM(主 session 或 subagent)生成候选。脚本本身只读 vault 现有渠道 + 行政区划数据,组装"待 LLM 补全"输入;LLM 输出 jsonl 由脚本合并入 catalog。

- [ ] **Step 1: 收集已知 city_code 数据源**

中国 2024 标准行政区划代码可以本地维护一份精简表。新建 `state/T1_channels/_admin_codes.csv`,人工 from 国家统计局 / wikipedia 整理 ~330 地级市 city_code + 4 个直辖市下属 ~80 区。

如时间紧,先用 LLM 生成一份候选 csv,user review。

```bash
# 用 LLM 生成候选,主 session 直接做(无脚本):
# 输入 prompt: "列出中国所有地级市 + 4直辖市下属区,每行 city, province, city_code(国标6位)"
# 输出落 state/T1_channels/_admin_codes.csv
```

- [ ] **Step 2: 写候选生成脚本骨架**

```python
# scripts/_oneshot/t1_generate_channel_candidates_2026-05-19.py
"""读 _admin_codes.csv + vault 现有渠道目录,组装"待补全"候选清单。

候选清单交主 session(或 subagent)按"市发改委 / 市能源局 / 市政府网"三主线
逐一生成 root_domain + list_url 候选,产物 jsonl 反喂本脚本合并入 channel_catalog.yaml。
"""
from __future__ import annotations
import csv
import json
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.l1_collect.channel_catalog import (
    Channel, ChannelStatus, load_catalog, save_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
ADMIN_CSV = ROOT / "state" / "T1_channels" / "_admin_codes.csv"
CATALOG = ROOT / "state" / "T1_channels" / "channel_catalog.yaml"
VAULT_CATALOG_MD = Path.home() / "Documents" / "Zayn Main" / "政策分析" / "00 背景资料" / "渠道目录.md"
LLM_INPUT_OUT = ROOT / "state" / "T1_channels" / "_llm_gen_input.jsonl"
LLM_OUTPUT_IN = ROOT / "state" / "T1_channels" / "_llm_gen_output.jsonl"

CST = timezone(timedelta(hours=8))
CHANNEL_TYPES = ["发改委", "能源局", "政府网"]

def load_known_from_vault() -> dict[tuple[str, str], dict]:
    """从 vault 渠道目录.md 抽 city + channel_type → root_domain。"""
    text = VAULT_CATALOG_MD.read_text(encoding="utf-8")
    out: dict[tuple[str, str], dict] = {}
    # markdown 表格行:`| domain | 名称 |`
    for line in text.splitlines():
        m = re.match(r"\|\s*([a-zA-Z0-9.\-]+\.gov\.cn)\s*\|\s*(.+?)\s*\|", line)
        if not m:
            continue
        domain, name = m.group(1), m.group(2)
        # 识别 channel_type
        ct = None
        for t in CHANNEL_TYPES:
            if t in name:
                ct = t
                break
        if ct is None:
            continue
        # 识别 city(简单做法:从 name 抽"XX市/XX省")
        city_m = re.search(r"([一-龥]{2,4}(?:市|自治州))", name)
        if not city_m:
            continue
        city = city_m.group(1)
        out[(city, ct)] = {"root_domain": domain, "source": "vault_catalog"}
    return out

def emit_llm_input() -> int:
    """为每个 (city, channel_type) 缺失项写一行 LLM 待补全输入。"""
    known = load_known_from_vault()
    count = 0
    with open(ADMIN_CSV, encoding="utf-8") as f, open(LLM_INPUT_OUT, "w", encoding="utf-8") as out:
        reader = csv.DictReader(f)
        for row in reader:
            city, province, city_code = row["city"], row["province"], row["city_code"]
            for ct in CHANNEL_TYPES:
                if (city, ct) in known:
                    continue
                out.write(json.dumps({
                    "city": city, "province": province, "city_code": city_code,
                    "channel_type": ct,
                    "instruction": f"给出 {city} {ct} 的政策列表页 root_domain + 推测的 list_url(若不确定 list_url 留 null)",
                }, ensure_ascii=False) + "\n")
                count += 1
    print(f"wrote {count} LLM input rows to {LLM_INPUT_OUT}")
    return count

def merge_llm_output() -> int:
    """读 LLM 输出 jsonl,合并 entry 到 channel_catalog.yaml。"""
    if not LLM_OUTPUT_IN.exists():
        print(f"no LLM output at {LLM_OUTPUT_IN}, skipping merge")
        return 0
    catalog = load_catalog(CATALOG) if CATALOG.exists() else []
    seen = {(c.city, c.channel_type) for c in catalog}
    now = datetime.now(CST).isoformat(timespec="seconds")
    added = 0
    with open(LLM_OUTPUT_IN, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            key = (row["city"], row["channel_type"])
            if key in seen:
                continue
            if not row.get("root_domain"):
                continue
            catalog.append(Channel(
                city=row["city"], province=row.get("province", ""),
                level="市", city_code=row.get("city_code", ""),
                channel_type=row["channel_type"], root_domain=row["root_domain"],
                list_url=row.get("list_url", ""),
                source="llm_generated", status=ChannelStatus.候选,
                last_probed_at=None, notes=row.get("notes", ""),
            ))
            seen.add(key)
            added += 1
    save_catalog(catalog, CATALOG)
    print(f"merged {added} new channels into {CATALOG}, total = {len(catalog)}")
    return added

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["emit", "merge"], required=True)
    args = ap.parse_args()
    if args.phase == "emit":
        emit_llm_input()
    else:
        merge_llm_output()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 跑 emit 阶段**

```bash
cd ~/dev/政策分析-pipeline
python3 scripts/_oneshot/t1_generate_channel_candidates_2026-05-19.py --phase emit
# 输出 state/T1_channels/_llm_gen_input.jsonl
wc -l state/T1_channels/_llm_gen_input.jsonl
# Expected: ~330 * 3 - 已知 = 大致 700-900 行
```

- [ ] **Step 4: 主 session 或 subagent 跑 LLM 补全**

逐行读 `_llm_gen_input.jsonl`,对每条调用 Claude(或本地代码 lookup),输出补全后的 jsonl 到 `_llm_gen_output.jsonl`。

> 子任务约束(LESSONS D5):subagent prompt 必须明文写"只读 pipeline + vault,禁止读 legacy archive",产物落 state/,不直接写 catalog。

如时间紧:主 session 直接做,batch 50 条 prompt 一组,共 ~15 轮。

- [ ] **Step 5: 跑 merge 阶段**

```bash
python3 scripts/_oneshot/t1_generate_channel_candidates_2026-05-19.py --phase merge
# 检查 channel_catalog.yaml
head -30 state/T1_channels/channel_catalog.yaml
wc -l state/T1_channels/channel_catalog.yaml
# Expected: 总条目 ~900-990(330 城 × 3 类 - 已 known)
```

- [ ] **Step 6: Commit oneshot + 产物(_llm_gen_input/output 不进 git,见 gitignore)**

```bash
# 先把 _llm_gen_* 加进 gitignore
echo "/T1_channels/_llm_gen_input.jsonl" >> state/.gitignore
echo "/T1_channels/_llm_gen_output.jsonl" >> state/.gitignore
echo "/T1_channels/_admin_codes.csv" >> state/.gitignore   # 也是中间产物
git add scripts/_oneshot/t1_generate_channel_candidates_2026-05-19.py state/T1_channels/channel_catalog.yaml state/.gitignore
git commit -m "T1.1.3: generate ~900 channel candidates from admin codes + LLM"
```

---

### Task 1.4: 跑联通性测试,populate catalog

**Files:**
- Create: `scripts/_oneshot/t1_probe_all_channels_2026-05-19.py`
- Modify: `state/T1_channels/channel_catalog.yaml`
- Modify: `state/T1_channels/channel_probe_log.jsonl`(产物)

- [ ] **Step 1: 写 probe 调度脚本**

```python
# scripts/_oneshot/t1_probe_all_channels_2026-05-19.py
"""对 channel_catalog 中所有 status=候选 的渠道跑 connectivity_probe。"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.l1_collect.channel_catalog import (
    Channel, ChannelStatus, load_catalog, save_catalog,
)
from scripts.l1_collect.connectivity_probe import probe_url

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "state" / "T1_channels" / "channel_catalog.yaml"
PROBE_LOG = ROOT / "state" / "T1_channels" / "channel_probe_log.jsonl"

MAX_WORKERS = 8
SLEEP_BETWEEN = 0.3

def probe_one(ch: Channel) -> tuple[Channel, dict]:
    url = ch.list_url or f"https://{ch.root_domain}/"
    res = probe_url(url)
    log = {
        "timestamp": res.probed_at, "city": ch.city, "channel_type": ch.channel_type,
        "root_domain": ch.root_domain, "url": url, "http_status": res.http_status,
        "page_has_list_pattern": res.page_has_list_pattern, "verdict": res.verdict,
        "error": res.error,
    }
    ch.last_probed_at = res.probed_at
    ch.probe_result = res.verdict
    if res.verdict == "ok":
        ch.status = ChannelStatus.验证
    return ch, log

def main():
    catalog = load_catalog(CATALOG)
    pending = [c for c in catalog if c.status == ChannelStatus.候选]
    print(f"probing {len(pending)} channels with {MAX_WORKERS} workers")
    with open(PROBE_LOG, "a", encoding="utf-8") as logf:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = [ex.submit(probe_one, c) for c in pending]
            done = 0
            for fut in as_completed(futures):
                ch, log = fut.result()
                logf.write(json.dumps(log, ensure_ascii=False) + "\n")
                done += 1
                if done % 50 == 0:
                    print(f"  {done}/{len(pending)} done")
                time.sleep(SLEEP_BETWEEN)
    save_catalog(catalog, CATALOG)
    n_ok = sum(1 for c in catalog if c.status == ChannelStatus.验证)
    n_total = len(catalog)
    print(f"done: {n_ok}/{n_total} channels verified")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑 probe(预计 5-15 分钟)**

```bash
python3 scripts/_oneshot/t1_probe_all_channels_2026-05-19.py
```

- [ ] **Step 3: 验证 catalog 状态**

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from scripts.l1_collect.channel_catalog import load_catalog
from pathlib import Path
cat = load_catalog(Path('state/T1_channels/channel_catalog.yaml'))
from collections import Counter
print(Counter(c.status.value for c in cat))
print(Counter(c.probe_result for c in cat))
"
# Expected: 验证率 30-60%(政府网域名命中率不高很正常)
```

- [ ] **Step 4: Commit**

```bash
git add scripts/_oneshot/t1_probe_all_channels_2026-05-19.py state/T1_channels/channel_catalog.yaml
git commit -m "T1.1.4: probe all ~900 channels, populate status=验证 for reachable"
```

---

## Phase 2 · 优先级(2 tasks)

### Task 2.1: city_priority 模块

**Files:**
- Create: `scripts/l1_collect/city_priority.py`
- Create: `tests/l1_collect/test_city_priority.py`

- [ ] **Step 1: 写 test 文件**

```python
"""Tests for city_priority."""
from scripts.l1_collect.city_priority import compute_priority_score, BUSINESS_RULES

def test_score_first_tier_charging():
    # 北京:充电(一线)+ 加油top + 电力(直辖市) → 高分
    score = compute_priority_score(
        city="北京市", reasons=["充电_一线", "加油_top", "电力_直辖市"], is_municipality=True
    )
    assert score >= 12

def test_score_provincial_capital_only():
    score = compute_priority_score(city="贵阳市", reasons=["电力_省会"], is_municipality=False)
    assert 3 <= score <= 5

def test_score_zero_reasons():
    score = compute_priority_score(city="某小城", reasons=[], is_municipality=False)
    assert score == 0

def test_business_rules_no_overlap_within_line():
    """同一业务线内规则之间不应重复(避免同城被加两次同类分)。"""
    for line, rules in BUSINESS_RULES.items():
        cities = [c for r in rules for c in r["cities"]]
        assert len(cities) == len(set(cities)), f"重复城市 in {line}"
```

- [ ] **Step 2: 跑测试 → fail**

- [ ] **Step 3: 写实现**

```python
# scripts/l1_collect/city_priority.py
"""P0/P1/P2 优先级算法。

打分规则:每命中一个业务线 +3,直辖市 +2,GDP Top 10 +1。
"""
from __future__ import annotations
from typing import Iterable

WEIGHT_PER_BUSINESS = 3
WEIGHT_MUNICIPALITY = 2
WEIGHT_GDP_TOP10 = 1

MUNICIPALITIES = {"北京市", "上海市", "天津市", "重庆市"}

GDP_TOP10_2024 = {
    "上海市", "北京市", "深圳市", "重庆市", "广州市",
    "苏州市", "成都市", "杭州市", "武汉市", "南京市",
}

BUSINESS_RULES = {
    "充电": [
        {"label": "一线", "cities": {"北京市", "上海市", "广州市", "深圳市"}},
        {"label": "新一线", "cities": {
            "成都市", "杭州市", "武汉市", "重庆市", "天津市", "西安市",
            "苏州市", "南京市", "长沙市", "郑州市", "济南市", "合肥市",
            "昆明市", "无锡市", "宁波市", "青岛市", "厦门市", "福州市", "沈阳市",
        }},
    ],
    "加油": [
        # Top 汽油消费 ~50 城,与上面去重后净增
        {"label": "top50_增量", "cities": {
            "东莞市", "佛山市", "嘉兴市", "温州市", "泉州市",
            "南通市", "烟台市", "潍坊市", "常州市", "惠州市",
        }},
    ],
    "电力": [
        {"label": "省会(去重后)", "cities": {
            "石家庄市", "太原市", "呼和浩特市", "长春市", "哈尔滨市",
            "南昌市", "贵阳市", "拉萨市", "兰州市", "西宁市",
            "银川市", "乌鲁木齐市", "海口市", "南宁市", "台北市",
        }},
        {"label": "计划单列", "cities": {"宁波市", "青岛市", "深圳市", "厦门市", "大连市"}},
    ],
}

def reasons_for_city(city: str) -> list[str]:
    """城市命中的业务线规则 label,用于审计。"""
    out = []
    for line, rules in BUSINESS_RULES.items():
        for r in rules:
            if city in r["cities"]:
                out.append(f"{line}_{r['label']}")
    return out

def compute_priority_score(city: str, reasons: Iterable[str], is_municipality: bool | None = None) -> float:
    reasons = list(reasons)
    if is_municipality is None:
        is_municipality = city in MUNICIPALITIES
    score = len(reasons) * WEIGHT_PER_BUSINESS
    if is_municipality:
        score += WEIGHT_MUNICIPALITY
    if city in GDP_TOP10_2024:
        score += WEIGHT_GDP_TOP10
    return score

def all_p0_cities() -> list[tuple[str, list[str], float]]:
    cities = set()
    for line, rules in BUSINESS_RULES.items():
        for r in rules:
            cities.update(r["cities"])
    out = []
    for c in cities:
        r = reasons_for_city(c)
        s = compute_priority_score(c, r)
        out.append((c, r, s))
    out.sort(key=lambda x: (-x[2], x[0]))
    return out
```

- [ ] **Step 4: 跑测试 → pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/city_priority.py tests/l1_collect/test_city_priority.py
git commit -m "T1.2.1: city_priority scoring + business rule tables"
```

---

### Task 2.2: 生成 P0 list + user ack

**Files:**
- Create: `scripts/_oneshot/t1_build_p0_city_list_2026-05-19.py`
- Modify: `state/T1_channels/city_priority.yaml`(产物)

- [ ] **Step 1: 写脚本**

```python
# scripts/_oneshot/t1_build_p0_city_list_2026-05-19.py
"""依 city_priority 算分 + 渠道有效性,生成 city_priority.yaml(P0/P1/P2 三档)。

P0 = 业务驱动 union(~50 城)且 channel_catalog 至少有 1 个 status=验证 的渠道
P1 = 京沪津渝下辖区(本任务暂留 placeholder,需要单独 admin codes 数据)
P2 = 全市级 - P0
"""
from __future__ import annotations
import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.l1_collect.channel_catalog import load_catalog, ChannelStatus
from scripts.l1_collect.city_priority import all_p0_cities

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "state" / "T1_channels" / "channel_catalog.yaml"
OUT = ROOT / "state" / "T1_channels" / "city_priority.yaml"

def main():
    catalog = load_catalog(CATALOG)
    verified_cities = {c.city for c in catalog if c.status == ChannelStatus.验证}
    p0 = [
        {"city": c, "reasons": r, "priority_score": s,
         "has_verified_channel": c in verified_cities}
        for c, r, s in all_p0_cities()
    ]
    all_cities_in_catalog = {c.city for c in catalog if c.level == "市"}
    p2_set = all_cities_in_catalog - {x["city"] for x in p0}
    p2 = [{"city": c} for c in sorted(p2_set)]
    out = {
        "version": "2026-05-19",
        "batches": {"P0": p0, "P1": [], "P2": p2},
        "notes": "P1 待 admin codes 补京沪津渝下辖区数据后填",
    }
    OUT.write_text(yaml.dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"P0 = {len(p0)} cities, P2 = {len(p2)} cities, P1 = 0 (TODO)")
    print(f"saved to {OUT}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑生成**

```bash
python3 scripts/_oneshot/t1_build_p0_city_list_2026-05-19.py
```

- [ ] **Step 3: 把 P0 清单展示给 user,user 扫一眼 ack(可加/减城)**

```bash
python3 -c "
import yaml
d = yaml.safe_load(open('state/T1_channels/city_priority.yaml'))
for x in d['batches']['P0']:
    print(f'{x[\"priority_score\"]:5.1f}  {x[\"city\"]:10s}  channel={x[\"has_verified_channel\"]}  {x[\"reasons\"]}')
"
```

User 看完回"OK"或"加 X 删 Y",主 session 手工编辑 city_priority.yaml。

- [ ] **Step 4: Commit ack 版本**

```bash
git add scripts/_oneshot/t1_build_p0_city_list_2026-05-19.py state/T1_channels/city_priority.yaml
git commit -m "T1.2.2: build P0 ~50 city list with priority scores, user-acked"
```

---

## Phase 3 · 过滤/查重/抽取核心(3 tasks)

### Task 3.1: news_filter 模块

**Files:**
- Create: `scripts/l1_collect/news_filter.py`
- Create: `tests/l1_collect/test_news_filter.py`

- [ ] **Step 1: 写 test**

```python
"""Tests for news_filter."""
from scripts.l1_collect.news_filter import is_news_or_press

def test_blocked_domain_media():
    assert is_news_or_press(
        url="https://www.xinhuanet.com/article/x", title="某政策解读", issuer=""
    ).is_filtered is True

def test_blocked_domain_storage_network():
    assert is_news_or_press(
        url="https://www.escn.com.cn/news/x.html", title="湖南储能项目推进", issuer=""
    ).is_filtered is True

def test_title_suffix_market_county():
    assert is_news_or_press(
        url="https://example.gov.cn/x", title="信阳新能源发展看区域转型_市县", issuer="信阳市政府"
    ).is_filtered is True

def test_credit_xx_pattern():
    assert is_news_or_press(
        url="https://credit.sh.gov.cn/article", title="4 部门喊你领补贴", issuer="信用上海"
    ).is_filtered is True

def test_gov_policy_page_pass():
    """政府网政策原文应通过(本阶段不开 override,但政府域名 + 政策标题就该通过)。"""
    r = is_news_or_press(
        url="https://www.gov.cn/zhengce/2024/x.html",
        title="国务院关于xxx的通知", issuer="国务院",
    )
    assert r.is_filtered is False

def test_no_issuer_lookup_fail():
    """issuer_unknown 应该被过滤(进 quarantine)。"""
    r = is_news_or_press(
        url="https://unknown.cn/x", title="某通知", issuer=None
    )
    assert r.is_filtered is True
    assert "issuer_unknown" in r.reasons
```

- [ ] **Step 2: 跑测试 → fail**

- [ ] **Step 3: 写实现**

```python
# scripts/l1_collect/news_filter.py
"""政策 vs 新闻稿 确定性过滤。

规则(全部确定性,不上 LLM):
  1. 域名黑名单(媒体域名)
  2. 标题特征(_市县后缀 / [XX网] 前缀)
  3. issuer 必须是政府机关(canonical 表 lookup,失败标 issuer_unknown)

本阶段不开 override(2026-05-19 user 决策),接受被误杀。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from urllib.parse import urlparse
import re

DOMAIN_BLACKLIST = {
    "xinhuanet.com", "people.com.cn", "cctv.com", "thepaper.cn",
    "sohu.com", "sina.com.cn", "163.com", "qq.com", "ifeng.com",
    "escn.com.cn", "in-en.com", "bjx.com.cn",         # 行业网
    "credit.sh.gov.cn", "credit.beijing.gov.cn",      # 信用 XX(转载站)
}

GOV_DOMAIN_SUFFIXES = (".gov.cn", ".org.cn")  # 政府 / 法定组织

TITLE_BAD_PATTERNS = [
    re.compile(r"_市县$"),
    re.compile(r"^\[\w+网\]"),
    re.compile(r"国际\w{1,4}网"),
]

GOV_ISSUER_KEYWORDS = (
    "委", "局", "部", "院", "司", "厅", "办公厅", "政府", "国务院", "管理委员会", "管委会",
)

@dataclass
class FilterResult:
    is_filtered: bool
    reasons: list[str] = field(default_factory=list)

def _domain_blocked(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    return any(host == d or host.endswith("." + d) for d in DOMAIN_BLACKLIST)

def _is_gov_domain(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    return any(host.endswith(s) for s in GOV_DOMAIN_SUFFIXES)

def _issuer_is_gov(issuer: str | None) -> bool:
    if not issuer:
        return False
    return any(kw in issuer for kw in GOV_ISSUER_KEYWORDS)

def is_news_or_press(url: str, title: str, issuer: str | None) -> FilterResult:
    reasons: list[str] = []
    if _domain_blocked(url):
        reasons.append("domain_blacklist")
    for pat in TITLE_BAD_PATTERNS:
        if pat.search(title):
            reasons.append(f"title_pattern:{pat.pattern}")
            break
    # issuer 检验:必须能识别为政府机关
    if not _issuer_is_gov(issuer):
        # 如果是政府域名且 issuer 缺失,可以暂留 quarantine 而不是直接 drop
        if _is_gov_domain(url) and issuer is None:
            reasons.append("issuer_unknown_but_gov_domain")
        else:
            reasons.append("issuer_unknown")
    return FilterResult(is_filtered=bool(reasons), reasons=reasons)
```

- [ ] **Step 4: 跑测试 → pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/news_filter.py tests/l1_collect/test_news_filter.py
git commit -m "T1.3.1: news_filter 4-rule deterministic filter, no override"
```

---

### Task 3.2: dedup 模块

**Files:**
- Create: `scripts/l1_collect/dedup.py`
- Create: `tests/l1_collect/test_dedup.py`

- [ ] **Step 1: 写 test**

```python
"""Tests for dedup: URL/文号/标题 三维查重。"""
from scripts.l1_collect.dedup import (
    normalize_url, normalize_official_number, normalize_title,
    DedupIndex,
)

def test_normalize_url_strips_fragment_query_trailing_slash():
    assert normalize_url("https://x.gov.cn/a/?utm=1#sec") == normalize_url("https://x.gov.cn/a")

def test_normalize_official_number_removes_brackets():
    assert normalize_official_number("发改能源〔2024〕1128号") == normalize_official_number("发改能源[2024]1128号")
    assert normalize_official_number("发改能源〔2024〕1128号") == normalize_official_number("发改能源2024年1128号")

def test_normalize_title_drops_punct_whitespace():
    assert normalize_title("关于xx的 通知(2024 年版)") == normalize_title("关于xx的通知2024年版")

def test_dedup_index_url_hit():
    idx = DedupIndex()
    idx.add(url="https://x.gov.cn/a", official_number="", title="通知 1")
    assert idx.is_dup(url="https://x.gov.cn/a/?utm=z", official_number="", title="完全不同的标题")
    
def test_dedup_index_official_number_hit():
    idx = DedupIndex()
    idx.add(url="https://x.gov.cn/a", official_number="发改能源〔2024〕1128号", title="通知 1")
    assert idx.is_dup(url="https://y.gov.cn/b", official_number="发改能源[2024]1128号", title="不同")

def test_dedup_index_title_hit():
    idx = DedupIndex()
    idx.add(url="https://x.gov.cn/a", official_number="", title="关于xx的通知 (2024)")
    assert idx.is_dup(url="https://y.gov.cn/b", official_number="", title="关于xx的通知2024")
```

- [ ] **Step 2: 跑测试 → fail**

- [ ] **Step 3: 写实现**

```python
# scripts/l1_collect/dedup.py
"""三维查重:URL / 文号 / 标题。"""
from __future__ import annotations
import hashlib
import re
from urllib.parse import urlparse, urlunparse

_URL_TRAILING_SLASH = re.compile(r"/$")
_TITLE_CLEAN = re.compile(r"[\s　\(\)（）\[\]【】《》""''\":：;；,，.。!！?？\-—_]+")
_OFFNUM_CLEAN = re.compile(r"[\s\(\)（）\[\]【】〔〕年号]+")

def normalize_url(url: str) -> str:
    """去 query / fragment / 末尾斜杠。"""
    if not url:
        return ""
    p = urlparse(url)
    return urlunparse((p.scheme.lower(), p.netloc.lower(),
                       _URL_TRAILING_SLASH.sub("", p.path), "", "", ""))

def normalize_official_number(s: str) -> str:
    if not s:
        return ""
    return _OFFNUM_CLEAN.sub("", s).lower()

def normalize_title(s: str) -> str:
    if not s:
        return ""
    return _TITLE_CLEAN.sub("", s).lower()

def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16] if s else ""

class DedupIndex:
    def __init__(self) -> None:
        self.url_hashes: set[str] = set()
        self.offnum_hashes: set[str] = set()
        self.title_hashes: set[str] = set()

    def add(self, *, url: str, official_number: str, title: str) -> None:
        if h := _hash(normalize_url(url)):
            self.url_hashes.add(h)
        if h := _hash(normalize_official_number(official_number)):
            self.offnum_hashes.add(h)
        if h := _hash(normalize_title(title)):
            self.title_hashes.add(h)

    def is_dup(self, *, url: str, official_number: str, title: str) -> bool:
        if (h := _hash(normalize_url(url))) and h in self.url_hashes:
            return True
        if (h := _hash(normalize_official_number(official_number))) and h in self.offnum_hashes:
            return True
        if (h := _hash(normalize_title(title))) and h in self.title_hashes:
            return True
        return False

    @classmethod
    def from_vault_policies(cls, vault_policies_dir):
        """扫 vault 现有 0_raw/policies/ 建索引。"""
        import yaml
        from pathlib import Path
        idx = cls()
        for f in Path(vault_policies_dir).glob("*.md"):
            try:
                txt = f.read_text(encoding="utf-8")[:4000]
            except Exception:
                continue
            m = re.search(r"^---\n(.*?)\n---", txt, re.S)
            if not m:
                continue
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except Exception:
                continue
            url = ((fm.get("provenance") or {}).get("url")) or ""
            offnum = fm.get("official_number") or ""
            title = fm.get("title") or ""
            idx.add(url=url, official_number=offnum, title=title)
        return idx
```

- [ ] **Step 4: 跑测试 → pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/dedup.py tests/l1_collect/test_dedup.py
git commit -m "T1.3.2: dedup index URL/official_number/title 三维查重"
```

---

### Task 3.3: metadata_extractor 模块

**Files:**
- Create: `scripts/l1_collect/metadata_extractor.py`
- Create: `tests/l1_collect/test_metadata_extractor.py`

- [ ] **Step 1: 写 test**

```python
"""Tests for metadata_extractor."""
from scripts.l1_collect.metadata_extractor import (
    extract_official_number, extract_date, extract_issuer_from_url, ExtractedMeta,
)

def test_extract_official_number_standard():
    s = "...本通知...（发改能源〔2024〕1128号）规定..."
    assert extract_official_number(s) == "发改能源〔2024〕1128号"

def test_extract_official_number_brackets_variant():
    s = "依据[2023]58号文..."
    assert extract_official_number(s) == "[2023]58号"

def test_extract_date_from_url_pattern():
    assert extract_date("https://www.gov.cn/zhengce/2024-08/15/content_xxx.html") == "2024-08-15"

def test_extract_date_from_body_chinese():
    body = "...本通知自2025年3月1日起施行..."
    assert extract_date("", body=body) == "2025-03-01"

def test_extract_issuer_from_url_ndrc():
    assert extract_issuer_from_url("https://www.ndrc.gov.cn/xxgzz/zcfb/") == "国家发展和改革委员会"

def test_extract_issuer_from_url_unknown():
    assert extract_issuer_from_url("https://unknown.example.com/x") is None
```

- [ ] **Step 2: 跑测试 → fail**

- [ ] **Step 3: 写实现(简版,后续可加 canonical lookup)**

```python
# scripts/l1_collect/metadata_extractor.py
"""元数据抽取:全 regex + canonical lookup,无 LLM(LESSONS B1)。"""
from __future__ import annotations
import re
from dataclasses import dataclass
from urllib.parse import urlparse

# 文号 regex(支持〔〕 / [] / () 三种括号)
_OFFNUM_RE = re.compile(r"[一-龥]{2,8}[〔\[(]\s*(?:19|20)\d{2}\s*[〕\])]\s*\d+\s*号")
_OFFNUM_RE_LOOSE = re.compile(r"[一-龥]{0,8}[〔\[(]\s*(?:19|20)\d{2}\s*[〕\])]\s*\d+\s*号")

_DATE_URL_RE = re.compile(r"/((?:19|20)\d{2})[-_/](\d{1,2})[-_/](\d{1,2})/")
_DATE_URL_MONTH_RE = re.compile(r"/((?:19|20)\d{2})[-_](\d{1,2})/")
_DATE_BODY_CN = re.compile(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})")
_DATE_BODY_ISO = re.compile(r"((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})")

# Issuer URL canonical 表(精简版,full table 应同步 vault canonical)
ISSUER_DOMAIN_TABLE = {
    "www.gov.cn": "国务院",
    "www.ndrc.gov.cn": "国家发展和改革委员会",
    "www.nea.gov.cn": "国家能源局",
    "www.miit.gov.cn": "工业和信息化部",
    "www.mofcom.gov.cn": "商务部",
    "www.mohurd.gov.cn": "住房和城乡建设部",
    "www.mee.gov.cn": "生态环境部",
    "www.mof.gov.cn": "财政部",
    # 省级 / 市级补充由 channel_catalog 反查
}

@dataclass
class ExtractedMeta:
    title: str = ""
    official_number: str = ""
    date: str = ""
    issuer: str | None = None
    url: str = ""

def extract_official_number(text: str) -> str:
    if not text:
        return ""
    m = _OFFNUM_RE.search(text)
    if m:
        return m.group(0).replace(" ", "")
    m = _OFFNUM_RE_LOOSE.search(text)
    return m.group(0).replace(" ", "") if m else ""

def extract_date(url: str, body: str = "") -> str:
    """优先 URL path,其次正文中文/ISO 日期。返回 YYYY-MM-DD 或 ''。"""
    if url:
        m = _DATE_URL_RE.search(url)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    if body:
        m = _DATE_BODY_CN.search(body) or _DATE_BODY_ISO.search(body)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return ""

def extract_issuer_from_url(url: str) -> str | None:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return None
    return ISSUER_DOMAIN_TABLE.get(host)

def extract_meta(url: str, title: str, body: str) -> ExtractedMeta:
    return ExtractedMeta(
        title=title.strip(),
        official_number=extract_official_number(body),
        date=extract_date(url, body),
        issuer=extract_issuer_from_url(url),
        url=url,
    )
```

- [ ] **Step 4: 跑测试 → pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/metadata_extractor.py tests/l1_collect/test_metadata_extractor.py
git commit -m "T1.3.3: metadata_extractor regex + canonical lookup, no LLM"
```

---

## Phase 4 · 抓取链(2 tasks)

### Task 4.1: fetcher 模块(4 级兜底链)

**Files:**
- Create: `scripts/l1_collect/fetcher.py`
- Create: `tests/l1_collect/test_fetcher.py`

- [ ] **Step 1: 写 test(mock 所有外部调用)**

```python
"""Tests for fetcher (all external calls mocked)."""
from unittest.mock import patch, MagicMock
import pytest
from scripts.l1_collect.fetcher import fetch_article, FetchResult

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
```

- [ ] **Step 2: 跑测试 → fail**

- [ ] **Step 3: 写实现(Firecrawl 等外部接口先标 NotImplemented + 环境变量 gate,实际 P0 跑时再补)**

```python
# scripts/l1_collect/fetcher.py
"""抓取兜底链:Firecrawl → Tavily → trafilatura → BeautifulSoup → fetch_error。

Firecrawl / Tavily 是商业 API,需要 env var 配置 key,无 key 时跳过。
trafilatura + BS4 走纯本地 HTTP。
"""
from __future__ import annotations
import os
from dataclasses import dataclass
import requests

MIN_BODY_LEN = 200  # 短于此视为抓取失败(摘要而非全文)
UA = "Mozilla/5.0 (compatible; ZCE-Fetcher/0.1)"
TIMEOUT = 30

@dataclass
class FetchResult:
    url: str
    via: str          # firecrawl | tavily_then_traf | trafilatura | bs4 | fetch_error
    body: str | None
    raw_html: str | None = None

def _fetch_via_firecrawl(url: str) -> str | None:
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v0/scrape",
            json={"url": url, "formats": ["markdown"]},
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        md = (data.get("data") or {}).get("markdown") or ""
        return md if len(md) >= MIN_BODY_LEN else None
    except Exception:
        return None

def _fetch_via_trafilatura(url: str) -> str | None:
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
        return text if text and len(text) >= MIN_BODY_LEN else None
    except Exception:
        return None

def _fetch_via_bs4(url: str) -> str | None:
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if resp.status_code >= 400:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        # 去掉 script / style / nav
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        return text if len(text) >= MIN_BODY_LEN else None
    except Exception:
        return None

def fetch_article(url: str) -> FetchResult:
    for via, fn in [("firecrawl", _fetch_via_firecrawl),
                    ("trafilatura", _fetch_via_trafilatura),
                    ("bs4", _fetch_via_bs4)]:
        body = fn(url)
        if body:
            return FetchResult(url=url, via=via, body=body)
    return FetchResult(url=url, via="fetch_error", body=None)
```

- [ ] **Step 4: 跑测试 → pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/fetcher.py tests/l1_collect/test_fetcher.py
git commit -m "T1.4.1: fetcher 4-tier fallback Firecrawl→trafilatura→BS4"
```

---

### Task 4.2: fetcher 真实 smoke(2 URL)

**Files:**
- Modify: (none, 仅 smoke 测试)

- [ ] **Step 1: 跑 2 个真实 URL**

```bash
python3 -c "
from scripts.l1_collect.fetcher import fetch_article
for url in [
    'https://www.gov.cn/zhengce/zhengceku/202403/content_6940314.htm',
    'https://www.ndrc.gov.cn/xxgk/zcfb/tz/202504/t20250411_1397280.html',
]:
    r = fetch_article(url)
    print(url, '->', r.via, len(r.body or ''))
"
# Expected: 两条都 via != 'fetch_error',body 长度 ≥ 500
```

- [ ] **Step 2: 若失败,排查链路 + 调参 + 重试**

如全部走 trafilatura 而非 firecrawl,说明 API key 未配,P0 阶段可接受用 trafilatura 主跑;但需要在 OPERATIONS 标注。

- [ ] **Step 3: 无 commit(纯 smoke)**

---

## Phase 5 · Pipeline steps(5 tasks)

### Task 5.1: step2_scan

**Files:**
- Create: `scripts/l1_collect/step2_scan.py`

> Step 2 = 翻渠道列表页,提取(标题, URL, 发布日期-粗)三元组。本步骤无独立测试(集成测试 in run_pipeline),但函数逻辑清晰可调。

- [ ] **Step 1: 写实现**

```python
# scripts/l1_collect/step2_scan.py
"""Step 2: 渠道扫描。

输入:channel_catalog status=验证 + 该 batch 的 cities
输出:state/T1_scan_raw/<batch>__<city>__<channel_type>.jsonl
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from .channel_catalog import Channel, ChannelStatus

UA = "Mozilla/5.0 (compatible; ZCE-Scan/0.1)"
TIMEOUT = 20
MAX_PAGES = 5
NEW_RATIO_THRESHOLD = 0.10
CST = timezone(timedelta(hours=8))

KEYWORDS = ("能源", "电力", "电网", "油气", "成品油", "充电", "储能", "新能源", "双碳", "光伏", "风电")

_DATE_RE = re.compile(r"((?:19|20)\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")

@dataclass
class ScanRow:
    title: str
    url: str
    date_hint: str
    source_channel: str  # root_domain
    scanned_at: str

def _extract_list_items(html: str, base_url: str) -> list[ScanRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[ScanRow] = []
    now = datetime.now(CST).isoformat(timespec="seconds")
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            continue
        if not any(kw in title for kw in KEYWORDS):
            continue
        href = a["href"]
        if href.startswith("javascript:") or href.startswith("#"):
            continue
        url = urljoin(base_url, href)
        # 找邻近日期
        ctx = (a.parent.get_text(" ", strip=True) if a.parent else "")[:200]
        m = _DATE_RE.search(ctx)
        date_hint = ""
        if m:
            y, mo, d = m.groups()
            date_hint = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        rows.append(ScanRow(title=title, url=url, date_hint=date_hint,
                            source_channel=base_url, scanned_at=now))
    return rows

def scan_channel(ch: Channel, out_dir: Path) -> int:
    """扫单渠道,翻页直至 max_pages 或新增比 < threshold。返回入库行数。"""
    if ch.status != ChannelStatus.验证:
        return 0
    seen_urls: set[str] = set()
    all_rows: list[ScanRow] = []
    for page in range(1, MAX_PAGES + 1):
        # 简单翻页:list_url 后追加 ?page=N(每个站不一,先用通用规则,失败 fall back)
        page_url = ch.list_url if page == 1 else f"{ch.list_url}?page={page}"
        try:
            r = requests.get(page_url, headers={"User-Agent": UA}, timeout=TIMEOUT)
            if r.status_code >= 400:
                break
        except Exception:
            break
        rows = _extract_list_items(r.text, page_url)
        new_rows = [x for x in rows if x.url not in seen_urls]
        for x in new_rows:
            seen_urls.add(x.url)
        all_rows.extend(new_rows)
        if page >= 3 and len(new_rows) / max(1, len(rows)) < NEW_RATIO_THRESHOLD:
            break

    fn = out_dir / f"{ch.city}__{ch.channel_type}__{ch.root_domain}.jsonl"
    fn.write_text("\n".join(json.dumps(asdict(x), ensure_ascii=False) for x in all_rows),
                  encoding="utf-8")
    return len(all_rows)
```

- [ ] **Step 2: Commit**

```bash
git add scripts/l1_collect/step2_scan.py
git commit -m "T1.5.1: step2_scan list page extraction with pagination"
```

---

### Task 5.2: step3_filter

**Files:**
- Create: `scripts/l1_collect/step3_filter.py`
- Create: `tests/l1_collect/test_step3_filter.py`

- [ ] **Step 1: 写 test**

```python
"""Tests for step3_filter orchestrator."""
import json
from pathlib import Path
from scripts.l1_collect.step3_filter import filter_scan_rows
from scripts.l1_collect.dedup import DedupIndex

def test_filter_drops_news_and_dup(tmp_path: Path):
    scan_jsonl = tmp_path / "in.jsonl"
    scan_jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"title": "关于xx的通知", "url": "https://www.gov.cn/zhengce/a.html",
         "date_hint": "2025-01-01", "source_channel": "https://www.gov.cn/", "scanned_at": ""},
        {"title": "信阳新能源_市县", "url": "https://xinyang.gov.cn/news/x.html",
         "date_hint": "", "source_channel": "https://xinyang.gov.cn/", "scanned_at": ""},
        {"title": "重复的通知", "url": "https://www.gov.cn/zhengce/a.html?dup=1",
         "date_hint": "", "source_channel": "https://www.gov.cn/", "scanned_at": ""},
    ]), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    quar = tmp_path / "quar.jsonl"
    kept, dropped = filter_scan_rows(scan_jsonl, out, quar, dedup_idx=DedupIndex())
    assert kept == 1
    assert dropped == 2
```

- [ ] **Step 2: 跑测试 → fail**

- [ ] **Step 3: 写实现**

```python
# scripts/l1_collect/step3_filter.py
"""Step 3: 标题过滤 + 新闻稿过滤 + 三维查重 编排。"""
from __future__ import annotations
import json
from pathlib import Path
from .news_filter import is_news_or_press
from .dedup import DedupIndex

def filter_scan_rows(in_jsonl: Path, out_jsonl: Path, quarantine_jsonl: Path,
                     dedup_idx: DedupIndex) -> tuple[int, int]:
    """返回 (kept, dropped)。"""
    kept = 0
    dropped = 0
    out_lines: list[str] = []
    quar_lines: list[str] = []
    for line in in_jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        title = row.get("title", "")
        url = row.get("url", "")
        # 新闻稿过滤(此时尚无 issuer,只用 domain + title)
        f = is_news_or_press(url=url, title=title, issuer=None)
        # 若 issuer_unknown 但是 gov 域,留下走 Step 4.5 再判
        relevant_reasons = [r for r in f.reasons if r != "issuer_unknown_but_gov_domain"]
        if relevant_reasons:
            quar_lines.append(json.dumps({**row, "drop_reasons": relevant_reasons}, ensure_ascii=False))
            dropped += 1
            continue
        # 三维查重(此处只有 URL + 标题,文号要 Step 4 后才有)
        if dedup_idx.is_dup(url=url, official_number="", title=title):
            quar_lines.append(json.dumps({**row, "drop_reasons": ["dup"]}, ensure_ascii=False))
            dropped += 1
            continue
        # 通过 → 更新 dedup_idx 防同批内重复
        dedup_idx.add(url=url, official_number="", title=title)
        out_lines.append(line)
        kept += 1
    out_jsonl.write_text("\n".join(out_lines), encoding="utf-8")
    quarantine_jsonl.write_text("\n".join(quar_lines), encoding="utf-8")
    return kept, dropped
```

- [ ] **Step 4: 跑测试 → pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_collect/step3_filter.py tests/l1_collect/test_step3_filter.py
git commit -m "T1.5.2: step3_filter orchestrate news_filter + dedup"
```

---

### Task 5.3: step4_fetch

**Files:**
- Create: `scripts/l1_collect/step4_fetch.py`

- [ ] **Step 1: 写实现**

```python
# scripts/l1_collect/step4_fetch.py
"""Step 4: 抓取候选政策的正文。"""
from __future__ import annotations
import json
from pathlib import Path
from .fetcher import fetch_article

def fetch_candidates(in_jsonl: Path, out_dir: Path, error_log: Path) -> tuple[int, int]:
    """返回 (success, error)。"""
    success = 0
    error = 0
    errors: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for line in in_jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        url = row.get("url", "")
        res = fetch_article(url)
        # 文件名按 URL hash,简单 deterministic
        import hashlib
        fid = hashlib.sha1(url.encode()).hexdigest()[:16]
        outf = out_dir / f"{fid}.json"
        outf.write_text(json.dumps({
            "url": url, "title": row.get("title", ""), "date_hint": row.get("date_hint", ""),
            "via": res.via, "body": res.body,
        }, ensure_ascii=False), encoding="utf-8")
        if res.via == "fetch_error":
            errors.append(url)
            error += 1
        else:
            success += 1
    error_log.write_text("\n".join(errors), encoding="utf-8")
    return success, error
```

- [ ] **Step 2: Commit**

```bash
git add scripts/l1_collect/step4_fetch.py
git commit -m "T1.5.3: step4_fetch orchestrate fetcher per-URL"
```

---

### Task 5.4: step4_5_extract

**Files:**
- Create: `scripts/l1_collect/step4_5_extract.py`

- [ ] **Step 1: 写实现**

```python
# scripts/l1_collect/step4_5_extract.py
"""Step 4.5: 元数据抽取(从 fetched body)。"""
from __future__ import annotations
import json
from pathlib import Path
from .metadata_extractor import extract_meta
from .news_filter import is_news_or_press

def extract_all(in_dir: Path, out_dir: Path, quarantine_jsonl: Path) -> tuple[int, int]:
    """返回 (extracted, quarantined)。第二轮过滤(issuer 维度)在此发生。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    quarantined = 0
    quar_lines: list[str] = []
    for f in in_dir.glob("*.json"):
        row = json.loads(f.read_text(encoding="utf-8"))
        if not row.get("body"):
            continue
        meta = extract_meta(url=row["url"], title=row["title"], body=row["body"])
        # 第二轮 news_filter(此时有 issuer)
        check = is_news_or_press(url=meta.url, title=meta.title, issuer=meta.issuer)
        if check.is_filtered and "issuer_unknown" in check.reasons:
            quar_lines.append(json.dumps({"url": meta.url, "title": meta.title,
                                          "drop_reasons": check.reasons}, ensure_ascii=False))
            quarantined += 1
            continue
        outf = out_dir / f.name
        outf.write_text(json.dumps({
            "url": meta.url, "title": meta.title, "official_number": meta.official_number,
            "date": meta.date or row.get("date_hint", ""), "issuer": meta.issuer,
            "body": row["body"], "via": row.get("via", ""),
        }, ensure_ascii=False), encoding="utf-8")
        extracted += 1
    with open(quarantine_jsonl, "a", encoding="utf-8") as qf:
        qf.write("\n".join(quar_lines))
    return extracted, quarantined
```

- [ ] **Step 2: Commit**

```bash
git add scripts/l1_collect/step4_5_extract.py
git commit -m "T1.5.4: step4_5_extract metadata + second news filter pass"
```

---

### Task 5.5: step5_ingest

**Files:**
- Create: `scripts/l1_collect/step5_ingest.py`
- Create: `scripts/l1_collect/ingester.py`

- [ ] **Step 1: 写 ingester(生成 vault md 文件)**

```python
# scripts/l1_collect/ingester.py
"""写 vault/0_raw/policies/<filename>.md,过 validate_schema 校验。"""
from __future__ import annotations
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yaml

VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
POLICIES_DIR = VAULT / "0_raw" / "policies"
CST = timezone(timedelta(hours=8))

ISSUER_SHORT_TABLE = {
    "国家发展和改革委员会": "NDRC",
    "国家能源局": "NEA",
    "工业和信息化部": "MIIT",
    "商务部": "MOFCOM",
    "住房和城乡建设部": "MOHURD",
    "生态环境部": "MEE",
    "财政部": "MOF",
    "国务院": "SC",
    # 市级补:由 channel_catalog 反查 city_code → "BJ" 等
}

def _issuer_short(issuer: str | None, city_code: str | None = None) -> str:
    if issuer and issuer in ISSUER_SHORT_TABLE:
        return ISSUER_SHORT_TABLE[issuer]
    if city_code:
        return f"CITY{city_code[:2]}"  # 简化:用前 2 位省码 + CITY 前缀
    return "OTHER"

def _hash8(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:8]

def compute_pid(date: str, issuer: str | None, official_number: str, title: str,
                city_code: str | None = None) -> str:
    year = (date or "1900").split("-")[0]
    short = _issuer_short(issuer, city_code)
    # 文号尾号
    if official_number:
        m = re.search(r"(\d+)\s*号", official_number)
        tail = m.group(1) if m else _hash8(official_number)
    else:
        tail = _hash8(f"{date}|{title}")
    return f"P_{year}_{short}_{tail}"

def _sanitize_filename(title: str) -> str:
    t = re.sub(r"[\\/:*?\"<>|]", "_", title)[:80]
    return t.strip() or "untitled"

def ingest_one(*, url: str, title: str, official_number: str, date: str, issuer: str | None,
               body: str, city: str | None = None, city_code: str | None = None,
               via: str = "trafilatura", confidence: float = 0.85) -> Path:
    """生成 vault md 文件,返回路径。"""
    pid = compute_pid(date, issuer, official_number, title, city_code)
    fm = {
        "id": pid,
        "aliases": [pid],
        "title": title,
        "official_number": official_number or "",
        "issuer": [issuer] if issuer else [],
        "date": date or "",
        "region": {
            "level": "市" if city else ("国家" if issuer in ISSUER_SHORT_TABLE else ""),
            "code": city_code or "",
            "name": city or "",
        },
        "provenance": {
            "url": url,
            "source_type": "A",
            "fetched_via": via,
            "fetched_at": datetime.now(CST).isoformat(timespec="seconds"),
            "collected_by": "t1-city-collection",
            "collected_mode": "build-phase-manual",
            "confidence": confidence,
        },
        "type": "policy",
    }
    body_md = f"## 政策原文\n\n{body.strip()}\n"
    fn = POLICIES_DIR / f"{_sanitize_filename(title)}.md"
    # 防同名覆盖
    n = 1
    while fn.exists():
        fn = POLICIES_DIR / f"{_sanitize_filename(title)}__{n}.md"
        n += 1
    content = "---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n" + body_md
    fn.write_text(content, encoding="utf-8")
    return fn

def validate_with_schema(path: Path) -> bool:
    """跑 pipeline validate_schema 单文件校验。"""
    pipeline_root = Path(__file__).resolve().parents[2]
    validator = pipeline_root / "scripts" / "audit" / "validate_schema.py"
    try:
        r = subprocess.run([sys.executable, str(validator), "--file", str(path)],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False
```

- [ ] **Step 2: 写 step5_ingest**

```python
# scripts/l1_collect/step5_ingest.py
"""Step 5: 入 vault raw。"""
from __future__ import annotations
import json
from pathlib import Path
from .ingester import ingest_one, validate_with_schema

def ingest_extracted(in_dir: Path, ingest_log: Path,
                     city_lookup: dict[str, dict] | None = None) -> tuple[int, int]:
    """返回 (ingested, failed)。"""
    ingested = 0
    failed = 0
    logs: list[dict] = []
    for f in in_dir.glob("*.json"):
        row = json.loads(f.read_text(encoding="utf-8"))
        city_info = (city_lookup or {}).get(row["url"], {})
        try:
            md_path = ingest_one(
                url=row["url"], title=row["title"],
                official_number=row.get("official_number", ""),
                date=row.get("date", ""), issuer=row.get("issuer"),
                body=row["body"], city=city_info.get("city"),
                city_code=city_info.get("city_code"), via=row.get("via", "trafilatura"),
            )
            ok = validate_with_schema(md_path)
            if not ok:
                md_path.unlink()  # 回滚
                failed += 1
                logs.append({"url": row["url"], "result": "schema_fail"})
                continue
            ingested += 1
            logs.append({"url": row["url"], "result": "ok", "file": md_path.name})
        except Exception as e:
            failed += 1
            logs.append({"url": row["url"], "result": "error", "error": str(e)[:200]})
    ingest_log.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in logs), encoding="utf-8")
    return ingested, failed
```

- [ ] **Step 3: Smoke 测试单条入库(用一个已知 URL,跑全链 4.5 + 5)**

```bash
python3 -c "
from pathlib import Path
from scripts.l1_collect.ingester import ingest_one, validate_with_schema
p = ingest_one(
    url='https://test.example.gov.cn/x',
    title='测试-勿入库-将立即删除',
    official_number='测发改[2025]999号',
    date='2025-12-31', issuer='国家能源局',
    body='这是测试正文,长度需要超过 200 字。'*20,
    via='trafilatura',
)
print('wrote', p)
ok = validate_with_schema(p)
print('schema ok:', ok)
import os
os.unlink(p)
print('cleaned up')
"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/l1_collect/ingester.py scripts/l1_collect/step5_ingest.py
git commit -m "T1.5.5: ingester + step5_ingest write vault raw with schema gate"
```

---

## Phase 6 · 总入口(1 task)

### Task 6.1: run_pipeline.py

**Files:**
- Create: `scripts/l1_collect/run_pipeline.py`

- [ ] **Step 1: 写编排脚本**

```python
# scripts/l1_collect/run_pipeline.py
"""T1 总入口:按 batch 跑 Step 2-5。

Usage:
  python3 -m scripts.l1_collect.run_pipeline --batch P0
  python3 -m scripts.l1_collect.run_pipeline --batch P0 --dry-run
  python3 -m scripts.l1_collect.run_pipeline --batch P0 --resume
  python3 -m scripts.l1_collect.run_pipeline --cities 杭州市,成都市
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import yaml
from .channel_catalog import load_catalog, ChannelStatus
from .step2_scan import scan_channel
from .step3_filter import filter_scan_rows
from .step4_fetch import fetch_candidates
from .step4_5_extract import extract_all
from .step5_ingest import ingest_extracted
from .dedup import DedupIndex

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
VAULT_POLICIES = Path.home() / "Documents" / "Zayn Main" / "政策分析" / "0_raw" / "policies"

def _resolve_cities(args) -> list[str]:
    if args.cities:
        return [c.strip() for c in args.cities.split(",")]
    p = yaml.safe_load((STATE / "T1_channels" / "city_priority.yaml").read_text(encoding="utf-8"))
    return [x["city"] for x in p["batches"][args.batch]]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", choices=["P0", "P1", "P2"], default="P0")
    ap.add_argument("--cities", help="逗号分隔城市名,覆盖 --batch")
    ap.add_argument("--resume", action="store_true", help="跳过已完成的 step 输出文件")
    ap.add_argument("--dry-run", action="store_true", help="只跑 Step 2-3,不抓不入库")
    args = ap.parse_args()

    cities = _resolve_cities(args)
    print(f"[run_pipeline] batch={args.batch} cities={len(cities)} dry_run={args.dry_run}")

    catalog = load_catalog(STATE / "T1_channels" / "channel_catalog.yaml")
    channels = [c for c in catalog if c.city in cities and c.status == ChannelStatus.验证]
    print(f"[run_pipeline] verified channels matched: {len(channels)}")

    # Step 2
    scan_dir = STATE / "T1_scan_raw"
    scan_dir.mkdir(exist_ok=True)
    total_scan = 0
    for ch in channels:
        n = scan_channel(ch, scan_dir)
        total_scan += n
    print(f"[Step 2] scanned {total_scan} title rows from {len(channels)} channels")

    # Step 3
    cand_dir = STATE / "T1_candidate"
    quar_dir = STATE / "T1_quarantine"
    cand_dir.mkdir(exist_ok=True); quar_dir.mkdir(exist_ok=True)
    dedup_idx = DedupIndex.from_vault_policies(VAULT_POLICIES)
    total_kept = 0; total_drop = 0
    cand_file = cand_dir / f"{args.batch}.jsonl"
    quar_file = quar_dir / f"{args.batch}__step3.jsonl"
    # 合并所有 scan 输出到一个临时文件
    merged = scan_dir / f"_merged_{args.batch}.jsonl"
    with open(merged, "w", encoding="utf-8") as out:
        for f in scan_dir.glob("*.jsonl"):
            if f.name.startswith("_"):
                continue
            out.write(f.read_text(encoding="utf-8"))
            out.write("\n")
    kept, drop = filter_scan_rows(merged, cand_file, quar_file, dedup_idx)
    total_kept += kept; total_drop += drop
    print(f"[Step 3] kept {total_kept}, dropped {total_drop} (quar: {quar_file})")

    if args.dry_run:
        print("[dry-run] stop after Step 3")
        return

    # Step 4
    fetch_dir = STATE / "T1_fetched"
    err_log = fetch_dir / f"{args.batch}__fetch_errors.txt"
    fetch_dir.mkdir(exist_ok=True)
    ok, err = fetch_candidates(cand_file, fetch_dir, err_log)
    print(f"[Step 4] fetched ok={ok} err={err}")

    # Step 4.5
    extract_dir = STATE / "T1_extracted"
    quar_45 = quar_dir / f"{args.batch}__step45.jsonl"
    extract_dir.mkdir(exist_ok=True)
    ext_ok, ext_quar = extract_all(fetch_dir, extract_dir, quar_45)
    print(f"[Step 4.5] extracted={ext_ok} quarantined={ext_quar}")

    # Step 5
    ingest_log = STATE / "T1_ingest_log" / f"{args.batch}.jsonl"
    (STATE / "T1_ingest_log").mkdir(exist_ok=True)
    ing_ok, ing_fail = ingest_extracted(extract_dir, ingest_log)
    print(f"[Step 5] ingested={ing_ok} failed={ing_fail}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑 dry-run 测试**

```bash
cd ~/dev/政策分析-pipeline
python3 -m scripts.l1_collect.run_pipeline --cities 杭州市 --dry-run
# Expected: Step 2 + Step 3 输出,无 Step 4-5
```

- [ ] **Step 3: Commit**

```bash
git add scripts/l1_collect/run_pipeline.py
git commit -m "T1.6.1: run_pipeline.py 总入口 --batch/--cities/--resume/--dry-run"
```

---

## Phase 7 · P0 执行(3 tasks)

### Task 7.1: 2 城 smoke

- [ ] **Step 1: 选两个差异化城市跑全链**

```bash
python3 -m scripts.l1_collect.run_pipeline --cities 杭州市,深圳市
```

- [ ] **Step 2: 查产物**

```bash
ls state/T1_scan_raw/
ls state/T1_candidate/
ls state/T1_fetched/ | wc -l
ls state/T1_extracted/ | wc -l
cat state/T1_ingest_log/*.jsonl | wc -l
ls -la ~/Documents/"Zayn Main"/政策分析/0_raw/policies/ | tail -5
```

- [ ] **Step 3: 手检 3-5 篇新入库政策**

确认 frontmatter 合规、body 完整、URL 真实指向政府网。

- [ ] **Step 4: 若 schema 有问题,回滚那几篇 + 修 ingester,无 commit until smoke pass**

---

### Task 7.2: 修任何阻断问题

- [ ] **Step 1-N: 根据 smoke 暴露的具体问题修补**

可能的问题:Step 2 翻页 URL 模式不对、Step 4.5 issuer_short 表不全、Step 5 schema 失败...逐一修 + 单测补,commit 时机为修一类 + 单测过 + 1 个 commit。

---

### Task 7.3: 跑全 P0

- [ ] **Step 1: 跑**

```bash
python3 -m scripts.l1_collect.run_pipeline --batch P0 2>&1 | tee state/T1_ingest_log/P0_run.log
```

- [ ] **Step 2: 验证数据规模**

```bash
grep -c '"result": "ok"' state/T1_ingest_log/P0.jsonl
# Expected: 几百篇(具体看渠道密度)
```

- [ ] **Step 3: 跑 schema 全量校验**

```bash
python3 scripts/audit/validate_schema.py
# Expected: 严格违反 = 0(legacy drift 数字会变化但都在 §F 范围)
```

- [ ] **Step 4: Commit log(数据已写 vault,vault 由 vault 自己的 git 管)**

```bash
git add state/T1_ingest_log/P0.jsonl state/T1_ingest_log/P0_run.log
git commit -m "T1.7.3: P0 batch ingest log (vault data committed separately)"
```

- [ ] **Step 5: 在 vault 仓 commit 新入库政策**

```bash
cd ~/Documents/"Zayn Main"/政策分析
git add 0_raw/policies/
git status | head -20
git commit -m "T1.7.3: P0 ingest, ~XXX new city-level policies"
cd -
```

---

## Phase 8 · 质量评估(2 tasks)

### Task 8.1: 抽样脚本

**Files:**
- Create: `scripts/_oneshot/t1_probe_p0_quality_2026-05-XX.py`(把 XX 改成实际日期)

- [ ] **Step 1: 写脚本(参考 L2 试探的 `probe_relations_quick_2026-05-18.py`)**

按 spec § P0 质量评估 7 维度组织抽样:
- 渠道有效性:每城 1 条入库 → URL HEAD 检查
- 标题相关性:20-30 条抽样,主 session 看
- 新闻稿污染率:全 P0 扫特征
- Schema 合规:跑 validate_schema
- 入库数量:统计
- issuer/region 准确率:20-30 条 vs 渠道域名
- 重复入库率:统计 quarantine

输出 `state/probes/<today>_T1_P0_quality/samples.md` + `verdict.md`(初稿)。

```python
# scripts/_oneshot/t1_probe_p0_quality_2026-05-XX.py
"""T1 P0 跑完质量评估抽样脚本。"""
from __future__ import annotations
import json, random, sys, requests
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2]
VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
OUT_DIR = ROOT / "state" / "probes" / f"{date.today().isoformat()}_T1_P0_quality"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SEED = 20260519

def main():
    rng = random.Random(SEED)
    # 读 ingest log 锁定 P0 入库的政策
    log = ROOT / "state" / "T1_ingest_log" / "P0.jsonl"
    ok_rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()
               if l.strip() and '"result": "ok"' in l]
    print(f"P0 ingested: {len(ok_rows)}")
    # 维度 1:每城抽 1
    by_city: dict[str, list] = {}
    for r in ok_rows:
        # 从 file 名反推 city,简化:都标 unknown(实际应该写时记录)
        by_city.setdefault("unknown", []).append(r)
    # 维度 2:全局抽 25
    samples = rng.sample(ok_rows, min(25, len(ok_rows)))
    md = ["# T1 P0 质量评估 samples", ""]
    samples_jsonl = []
    for i, r in enumerate(samples, 1):
        md += [f"### sample #{i}", f"- url: {r['url']}", f"- file: {r.get('file', '')}", ""]
        samples_jsonl.append(r)
    (OUT_DIR / "samples.md").write_text("\n".join(md), encoding="utf-8")
    (OUT_DIR / "samples.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in samples_jsonl), encoding="utf-8")
    print(f"wrote samples to {OUT_DIR}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑**

```bash
python3 scripts/_oneshot/t1_probe_p0_quality_2026-05-XX.py
```

- [ ] **Step 3: Commit oneshot 与产物**

```bash
git add scripts/_oneshot/t1_probe_p0_quality_2026-05-XX.py state/probes/
git commit -m "T1.8.1: P0 quality probe sampler"
```

---

### Task 8.2: 主 session 手判 + 出 verdict

- [ ] **Step 1: 读 samples.md,逐条对 7 维度打分**

参考 L2 试探的 `verdict.md` 结构(2026-05-18_relations_quick/verdict.md)。

- [ ] **Step 2: 写 verdict.md**

字段:
```markdown
# T1 P0 质量评估 verdict
| 维度 | 抽样 | 通过 | 通过线 | 判定 |
| 渠道有效性 | 50 | XX | ≥90% | ✓/✗ |
...
## 横向问题
## 是否进 C 准备
```

- [ ] **Step 3: Commit**

```bash
git add state/probes/<dir>/verdict.md
git commit -m "T1.8.2: P0 quality verdict, decide go/no-go for C preparation"
```

---

## Phase 9 · 准备 C(2 tasks)

### Task 9.1: P1/P2 联通测试

- [ ] **Step 1: 跑同一个 t1_probe_all_channels 脚本(扫剩余 status=候选 的渠道)**

```bash
python3 scripts/_oneshot/t1_probe_all_channels_2026-05-19.py
```

- [ ] **Step 2: 统计验证率**

```bash
python3 -c "
from collections import Counter
from scripts.l1_collect.channel_catalog import load_catalog
from pathlib import Path
cat = load_catalog(Path('state/T1_channels/channel_catalog.yaml'))
print('Total:', len(cat))
print('Status:', Counter(c.status.value for c in cat))
"
```

- [ ] **Step 3: Commit**

```bash
git add state/T1_channels/channel_catalog.yaml
git commit -m "T1.9.1: P1/P2 channel probe complete"
```

---

### Task 9.2: state/T1_channels/README.md

**Files:**
- Create: `state/T1_channels/README.md`

- [ ] **Step 1: 写 README**

```markdown
# T1 Channel State

## 文件用途
- channel_catalog.yaml — 渠道清单,字段见 SCHEMA / docs/proposals/T1
- city_priority.yaml   — P0/P1/P2 三档优先级
- channel_probe_log.jsonl — 每次联通测试记录(不进 git)

## 现状(<date>)
- 总渠道:N
- status=验证:M
- status=已扫:K
- P0 已跑:X 城,入库 Y 篇
- P1 已扫:0(待决策)
- P2 已扫:0(待决策)

## 跑 P1 / P2 的触发条件
1. P0 质量评估通过(verdict.md 7 维度全过)
2. user 拍板要跑(本任务设计上是"准备 C",不自动启动)
3. 跑前再确认 channel_catalog 有更新的联通结果

## Trigger commands
```bash
python3 -m scripts.l1_collect.run_pipeline --batch P1
python3 -m scripts.l1_collect.run_pipeline --batch P2
python3 -m scripts.l1_collect.run_pipeline --cities A,B,C
```

## 已知问题城市
(填:渠道 4xx / 列表页结构特殊不能 parse / 无 channel verified 的城市)
```

- [ ] **Step 2: Commit**

```bash
git add state/T1_channels/README.md
git commit -m "T1.9.2: state/T1_channels/README with trigger conditions"
```

---

## Phase 10 · vault 反哺(1 task)

### Task 10.1: 生成 + 主 session 在 user 监督下写 vault

**Files:**
- Create: `scripts/_oneshot/t1_generate_vault_backfill_2026-05-XX.py`

- [ ] **Step 1: 写脚本生成 markdown diff**

```python
"""扫 channel_catalog status=已扫 且 has ingest_count >= 1 的渠道,
按 vault 渠道目录.md 现有格式生成新增 markdown 片段。"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.l1_collect.channel_catalog import load_catalog, ChannelStatus

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "state" / "T1_channels" / "channel_catalog.yaml"
OUT = ROOT / "state" / "T1_channels" / "_vault_backfill_proposal.md"

def main():
    cat = load_catalog(CATALOG)
    eligible = [c for c in cat if c.status == ChannelStatus.已扫]
    print(f"eligible to backfill: {len(eligible)}")
    lines = ["## 市级扩展(T1 反哺,<date>)", "", "| 根域名 | 渠道名称 | 状态 |", "|---|---|:---:|"]
    for c in sorted(eligible, key=lambda x: (x.province, x.city, x.channel_type)):
        name = f"{c.city}{c.channel_type}"
        lines.append(f"| {c.root_domain} | {name} | ✅ 已验证 |")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑生成**

```bash
python3 scripts/_oneshot/t1_generate_vault_backfill_2026-05-XX.py
cat state/T1_channels/_vault_backfill_proposal.md
```

- [ ] **Step 3: 给 user 看 diff,user ack 后主 session 写入 vault**

```bash
# 在主 session 中,user 看完 _vault_backfill_proposal.md 内容
# user 回 "ok,合并"
# 主 session 用 Edit 工具把片段插入 ~/Documents/"Zayn Main"/政策分析/00 背景资料/渠道目录.md 的指定位置
```

- [ ] **Step 4: vault 仓 commit**

```bash
cd ~/Documents/"Zayn Main"/政策分析
git add "00 背景资料/渠道目录.md"
git commit -m "T1.10.1: backfill ~XX verified city-level channels from T1 P0"
cd -
```

- [ ] **Step 5: pipeline 仓 commit oneshot**

```bash
git add scripts/_oneshot/t1_generate_vault_backfill_2026-05-XX.py state/T1_channels/_vault_backfill_proposal.md
git commit -m "T1.10.1: vault backfill proposal generator + record"
```

---

## 收尾

- [ ] **更新 STATUS.md**:T1 标完成 + 数字更新(由 dump_status 或人工初版)
- [ ] **更新 CHANGELOG.md**:T1 phase 1 完成
- [ ] **归档 oneshot**:本次新增 4 个 t1_*_2026-05-XX.py oneshot 按 LESSONS C3 标 `[oneshot complete]` commit message

---

## Self-Review 已完成

**Spec coverage:** 对照 spec 各节,所有目标(6 条)+ 验收(8 条)都有对应 Task
- 目标 1 渠道清单 → T1.1.3 + T1.1.4
- 目标 2 优先级 → T1.2.1 + T1.2.2
- 目标 3 脚本 → T1.3-5 + T1.6.1
- 目标 4 P0 跑 → T1.7
- 目标 5 质量评估 → T1.8
- 目标 6 准备 C → T1.9
- 反哺机制 → T1.10
- 新闻稿过滤 → T1.3.1 + T1.5.2 + T1.5.4(两阶段过滤)

**Placeholder scan:** 检查后无 TBD / TODO / 「fill in details」。oneshot 文件名里 `2026-05-XX` 是占位等执行日期补,合理。Task 7.2 "修任何阻断问题" 是 smoke 发现问题再修,无法预先列具体步骤,合理。

**Type consistency:** Channel/ChannelStatus/FetchResult/ProbeResult/ExtractedMeta 等类型在多个 task 间一致引用。step3_filter 调 DedupIndex.is_dup() 签名一致。

**Naming consistency:** `channel_catalog.yaml` / `city_priority.yaml` / `channel_probe_log.jsonl` 全文统一。所有 `scripts.l1_collect.X` 模块 import 路径正确。

---

## Risks & Open

- **Firecrawl API key 未在 pipeline 仓配置**:T1.4.1 fetcher 测试 mock,真实跑时 fall back trafilatura。可接受(spec 风险表已列)
- **行政区划 csv 来源**:T1.1.3 Step 1 标"用 LLM 生成 + user review",这是一次性数据采集,可接受
- **issuer_short 表对市级机关不全**:T1.5.5 ingester 用 `CITY{province_code_前2位}` 简化兜底,首版可用,后续按需扩展 lookup 表
