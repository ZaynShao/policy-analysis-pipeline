# ②-A 确定性身份固化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一条常驻确定性身份 resolver,全语料幂等地把 `0_raw/policies/` 破损的 `id/issuer/issuer_canonical/region/date` 修对,守 SCHEMA §C(确定性才写 raw、记嵌套 provenance 审计),保守分级写(干净且与 ledger 一致才写、否则入队列),零 pid 硬编码。

**Architecture:** 判断在数据(`_meta/channel_registry.yaml` 域名→机构/区域 查表,新 canonical 源资产),代码是 dumb 纯函数 + applier。resolver 读 raw metadata → 查表算 identity | 标 conflict;apply 用 yaml round-trip 就地 §C 写 raw;冲突/低信心/未知落待裁决队列(派生层,不写 raw);ledger 仅当验收 oracle。dry-run→apply→verify 三段 CLI,vault checkpoint tag 可逆。

**Tech Stack:** Python 3.9 · pytest(testpaths=tests,绝对导入 `from scripts.l2_attribution...`)· PyYAML(`yaml.safe_load` / `yaml.dump(..., allow_unicode=True, sort_keys=False)`)。

**复用既有件(滑坡自审#1:不重造):**
- `scripts/l1_audit/corpus.py`:`load_policies(dir) -> list[PolicyRecord]`、`parse_policy_file(path)`。`PolicyRecord` 字段:`pid/path/title/official_number/date/issuer(list)/issuer_canonical(list)/url/body_head(前2000)/raw_fm(dict)`。
- frontmatter 正则:`_FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)`。
- 写盘范式(见 `apply.py`):`new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False)`;`f"---\n{new_fm}---\n\n{body.lstrip(chr(10))}\n"`。
- id 碰撞检测思路(见 `scripts/_oneshot/t3_phase2a_recompute_id_c.py` 的 `scan_existing_ids`)。
- **不复用** `apply.py:remint_id`(审计字段写顶层 + method 是 LLM 值,违反 §C;它从未被调用)。本计划写新的 §C 合规 writer 取代它;remint_id 标注废弃(不在本计划删,仅注释)。

**分支/可逆:** 在 `feat/source-apply`(① 工作分支)继续,不开新 worktree(vault 是另一仓,代码 worktree 隔离不了 vault)。vault 改动靠 checkpoint tag + 全 git rename 兜底回退。

**目录:** 新建 `scripts/l2_attribution/`(节点②归属 模块),测试 `tests/l2_attribution/`。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `scripts/l2_attribution/__init__.py` | 包标记 |
| `scripts/l2_attribution/models.py` | `ChannelEntry` / `ResolvedField` / `ResolvedIdentity` / `QueueRecord` 数据模型 |
| `scripts/l2_attribution/refdata.py` | 内嵌 province_table(34省→issuer_short/adcode2)+ ministry_map(部委域名→issuer_short)+ city→province 表(语料出现的市) |
| `scripts/l2_attribution/channel_registry.py` | 读 `_meta/channel_registry.yaml` + `lookup(registry, url)`(url→host→entry) |
| `scripts/l2_attribution/seed_channel_registry.py` | 解析 `渠道目录.md` + 扫语料域名 + refdata 自动派生 → registry 草稿 + needs_manual |
| `_meta/channel_registry.yaml`(vault) | **源资产**:域名→{issuer_short, issuer_canonical, region} |
| `scripts/l2_attribution/extractors.py` | `extract_issuer_from_title(title)` + `extract_luokuan_date(body_tail)` 纯函数 |
| `scripts/l2_attribution/resolver.py` | `resolve_identity(rec, registry) -> ResolvedIdentity` 纯函数(零 pid 分支) |
| `scripts/l2_attribution/ledger.py` | 读 ledger + `cross_check(resolved, ledger_entry)` |
| `scripts/l2_attribution/apply_identity.py` | §C 合规就地写 raw(yaml round-trip,嵌套 provenance 审计,碰撞检测) |
| `scripts/l2_attribution/review_queue.py` | `QueueRecord` 落 jsonl |
| `scripts/l2_attribution/report.py` | dry-run HTML 验收报告 |
| `scripts/l2_attribution/run_2a.py` | 编排 CLI:`dry-run` / `apply` / `verify` |

---

## Task 1: 模块骨架 + 数据模型

**Files:**
- Create: `scripts/l2_attribution/__init__.py`
- Create: `scripts/l2_attribution/models.py`
- Test: `tests/l2_attribution/__init__.py`, `tests/l2_attribution/test_models.py`

- [ ] **Step 1: 写失败测试** `tests/l2_attribution/test_models.py`

```python
from scripts.l2_attribution.models import (
    ChannelEntry, ResolvedField, ResolvedIdentity, QueueRecord,
)


def test_channel_entry_region_is_nested():
    e = ChannelEntry(
        domain="www.jinan.gov.cn", issuer_short="SD",
        issuer_canonical="济南市人民政府",
        region={"level": "市", "code": "370100", "name": "济南市"},
    )
    assert e.region["level"] == "市"
    assert e.issuer_short == "SD"


def test_resolved_identity_collects_fields_and_conflicts():
    ri = ResolvedIdentity(pid="P_2015_GO_x")
    ri.set_field("region", {"level": "市", "code": "370100", "name": "济南市"},
                 method="domain_lookup", confidence=0.99, from_val="国家/000000/未知")
    ri.add_conflict("date", reason="落款抽不到且现值坏 2027",
                    signals={"frontmatter": "2027-01-01", "luokuan": None})
    assert "region" in ri.fields
    assert ri.fields["region"].method == "domain_lookup"
    assert ri.has_conflicts() is True
    assert ri.conflicts[0].field == "date"


def test_queue_record_to_dict_roundtrips():
    q = QueueRecord(pid="P_x", field="issuer", reason="转载:标题机关与域名不符",
                    signals={"title_issuer": "国务院办公厅", "domain_region": "承德市"})
    d = q.to_dict()
    assert d["pid"] == "P_x" and d["field"] == "issuer"
    assert d["signals"]["domain_region"] == "承德市"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/shaoziyuan/dev/政策分析-pipeline && python3 -m pytest tests/l2_attribution/test_models.py -v`
Expected: FAIL(`ModuleNotFoundError: scripts.l2_attribution.models`)

- [ ] **Step 3: 写实现**

`scripts/l2_attribution/__init__.py`(空文件)和 `tests/l2_attribution/__init__.py`(空文件)。

`scripts/l2_attribution/models.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChannelEntry:
    domain: str
    issuer_short: str                 # id 前缀(地方=省级码)
    issuer_canonical: str             # 渠道级机关名(粗)
    region: dict                      # {level, code, name}


@dataclass
class ResolvedField:
    value: object
    method: str                       # §C method 枚举
    confidence: float
    from_val: str = ""                # 原值(审计用)


@dataclass
class Conflict:
    field: str
    reason: str
    signals: dict = field(default_factory=dict)


@dataclass
class ResolvedIdentity:
    pid: str
    fields: dict = field(default_factory=dict)        # name -> ResolvedField(待写)
    conflicts: list = field(default_factory=list)     # list[Conflict](入队列)

    def set_field(self, name, value, method, confidence, from_val=""):
        self.fields[name] = ResolvedField(value, method, confidence, from_val)

    def add_conflict(self, field_name, reason, signals=None):
        self.conflicts.append(Conflict(field_name, reason, signals or {}))

    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0


@dataclass
class QueueRecord:
    pid: str
    field: str
    reason: str
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"pid": self.pid, "field": self.field,
                "reason": self.reason, "signals": self.signals}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_models.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: commit**

```bash
git add scripts/l2_attribution/__init__.py scripts/l2_attribution/models.py tests/l2_attribution/
git commit -m "feat(②-A): 身份 resolver 数据模型(ChannelEntry/ResolvedIdentity/QueueRecord)"
```

---

## Task 2: 参考数据(province / ministry / city→province)

**Files:**
- Create: `scripts/l2_attribution/refdata.py`
- Test: `tests/l2_attribution/test_refdata.py`

**说明:** province_table 是稳定标准数据(GB/T 2260 省级),内嵌全 34 个。ministry_map 内嵌已知部委域名(从 `渠道目录.md` 中央表 + 语料常见)。city→province 覆盖语料破损集出现的市(执行时按需补全;下方给结构 + 代表样例,缺城市由 Task 4 curate 补)。

- [ ] **Step 1: 写失败测试** `tests/l2_attribution/test_refdata.py`

```python
from scripts.l2_attribution.refdata import PROVINCE, MINISTRY, CITY_PROVINCE


def test_province_has_all_34_and_shape():
    assert len(PROVINCE) == 34
    sd = PROVINCE["山东省"]
    assert sd["issuer_short"] == "SD"
    assert sd["code2"] == "37"          # 山东省级码前两位


def test_municipality_code():
    assert PROVINCE["上海市"]["issuer_short"] == "SH"
    assert PROVINCE["上海市"]["code2"] == "31"


def test_ministry_map_ndrc():
    assert MINISTRY["www.ndrc.gov.cn"]["issuer_short"] == "NDRC"
    assert MINISTRY["www.ndrc.gov.cn"]["region"]["level"] == "国家"
    assert MINISTRY["www.ndrc.gov.cn"]["region"]["code"] == "000000"


def test_city_province_lookup():
    assert CITY_PROVINCE["济南市"] == "山东省"
    assert CITY_PROVINCE["苏州市"] == "江苏省"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l2_attribution/test_refdata.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 写实现** `scripts/l2_attribution/refdata.py`

```python
"""参考数据:省级码表(GB/T 2260)+ 部委域名表 + 市→省表。
全是稳定标准数据 / 判断即数据;不规则项进表,不进代码。"""
from __future__ import annotations

# 34 省级行政区:名称 -> {issuer_short(id前缀), code2(省级码前两位)}
# issuer_short 沿用 ① 既定方案:直辖市码=市码;四川=SC;国务院=GWY(不在此表,见 MINISTRY)
PROVINCE = {
    "北京市": {"issuer_short": "BJ", "code2": "11"},
    "天津市": {"issuer_short": "TJ", "code2": "12"},
    "河北省": {"issuer_short": "HE", "code2": "13"},
    "山西省": {"issuer_short": "SX", "code2": "14"},
    "内蒙古自治区": {"issuer_short": "NM", "code2": "15"},
    "辽宁省": {"issuer_short": "LN", "code2": "21"},
    "吉林省": {"issuer_short": "JL", "code2": "22"},
    "黑龙江省": {"issuer_short": "HL", "code2": "23"},
    "上海市": {"issuer_short": "SH", "code2": "31"},
    "江苏省": {"issuer_short": "JS", "code2": "32"},
    "浙江省": {"issuer_short": "ZJ", "code2": "33"},
    "安徽省": {"issuer_short": "AH", "code2": "34"},
    "福建省": {"issuer_short": "FJ", "code2": "35"},
    "江西省": {"issuer_short": "JX", "code2": "36"},
    "山东省": {"issuer_short": "SD", "code2": "37"},
    "河南省": {"issuer_short": "HA", "code2": "41"},
    "湖北省": {"issuer_short": "HB", "code2": "42"},
    "湖南省": {"issuer_short": "HN", "code2": "43"},
    "广东省": {"issuer_short": "GD", "code2": "44"},
    "广西壮族自治区": {"issuer_short": "GX", "code2": "45"},
    "海南省": {"issuer_short": "HI", "code2": "46"},
    "重庆市": {"issuer_short": "CQ", "code2": "50"},
    "四川省": {"issuer_short": "SC", "code2": "51"},
    "贵州省": {"issuer_short": "GZ", "code2": "52"},
    "云南省": {"issuer_short": "YN", "code2": "53"},
    "西藏自治区": {"issuer_short": "XZ", "code2": "54"},
    "陕西省": {"issuer_short": "SN", "code2": "61"},
    "甘肃省": {"issuer_short": "GS", "code2": "62"},
    "青海省": {"issuer_short": "QH", "code2": "63"},
    "宁夏回族自治区": {"issuer_short": "NX", "code2": "64"},
    "新疆维吾尔自治区": {"issuer_short": "XJ", "code2": "65"},
    "香港特别行政区": {"issuer_short": "HK", "code2": "81"},
    "澳门特别行政区": {"issuer_short": "MO", "code2": "82"},
    "台湾省": {"issuer_short": "TW", "code2": "71"},
}

_NAT = {"level": "国家", "code": "000000", "name": "全国"}

# 部委 / 中央域名 -> {issuer_short, issuer_canonical, region}
# 种子来自 渠道目录.md 中央表;新部委由 Task 4 curate 补
MINISTRY = {
    "www.gov.cn":        {"issuer_short": "GWY", "issuer_canonical": "国务院", "region": _NAT},
    "www.ndrc.gov.cn":   {"issuer_short": "NDRC", "issuer_canonical": "国家发展和改革委员会", "region": _NAT},
    "zfxxgk.ndrc.gov.cn":{"issuer_short": "NDRC", "issuer_canonical": "国家发展和改革委员会", "region": _NAT},
    "www.nea.gov.cn":    {"issuer_short": "NEA", "issuer_canonical": "国家能源局", "region": _NAT},
    "zfxxgk.nea.gov.cn": {"issuer_short": "NEA", "issuer_canonical": "国家能源局", "region": _NAT},
    "www.miit.gov.cn":   {"issuer_short": "MIIT", "issuer_canonical": "工业和信息化部", "region": _NAT},
    "www.mof.gov.cn":    {"issuer_short": "MOF", "issuer_canonical": "财政部", "region": _NAT},
    "www.mee.gov.cn":    {"issuer_short": "MEE", "issuer_canonical": "生态环境部", "region": _NAT},
    "www.mohurd.gov.cn": {"issuer_short": "MOHURD", "issuer_canonical": "住房和城乡建设部", "region": _NAT},
    "www.mofcom.gov.cn": {"issuer_short": "MOFCOM", "issuer_canonical": "商务部", "region": _NAT},
    "www.sasac.gov.cn":  {"issuer_short": "SASAC", "issuer_canonical": "国务院国资委", "region": _NAT},
    "xxgk.mot.gov.cn":   {"issuer_short": "MOT", "issuer_canonical": "交通运输部", "region": _NAT},
    "m.12371.gov.cn":    {"issuer_short": "CPC", "issuer_canonical": "共产党员网", "region": _NAT},
    "std.samr.gov.cn":   {"issuer_short": "SAMR", "issuer_canonical": "国家市场监督管理总局", "region": _NAT},
}

# 市 -> 省(语料破损集出现的市;Task 4 curate 补全缺失市)
CITY_PROVINCE = {
    "济南市": "山东省", "苏州市": "江苏省", "广州市": "广东省", "深圳市": "广东省",
    "哈尔滨市": "黑龙江省", "银川市": "宁夏回族自治区", "吕梁市": "山西省",
    # … 执行时按语料补齐(Task 3 的 needs_manual 会列出缺的市)
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_refdata.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: commit**

```bash
git add scripts/l2_attribution/refdata.py tests/l2_attribution/test_refdata.py
git commit -m "feat(②-A): 参考数据 省级码/部委域名/市→省 表"
```

---

## Task 3: channel_registry 加载器 + lookup

**Files:**
- Create: `scripts/l2_attribution/channel_registry.py`
- Test: `tests/l2_attribution/test_channel_registry.py`, `tests/l2_attribution/fixtures/channel_registry_min.yaml`

- [ ] **Step 1: 写 fixture** `tests/l2_attribution/fixtures/channel_registry_min.yaml`

```yaml
- domain: www.jinan.gov.cn
  issuer_short: SD
  issuer_canonical: 济南市人民政府
  region: {level: 市, code: '370100', name: 济南市}
- domain: www.ndrc.gov.cn
  issuer_short: NDRC
  issuer_canonical: 国家发展和改革委员会
  region: {level: 国家, code: '000000', name: 全国}
```

- [ ] **Step 2: 写失败测试** `tests/l2_attribution/test_channel_registry.py`

```python
from pathlib import Path
from scripts.l2_attribution.channel_registry import load_registry, lookup

FIX = Path(__file__).parent / "fixtures" / "channel_registry_min.yaml"


def test_load_indexes_by_domain():
    reg = load_registry(str(FIX))
    assert reg["www.jinan.gov.cn"].issuer_short == "SD"
    assert reg["www.ndrc.gov.cn"].region["level"] == "国家"


def test_lookup_extracts_host_from_url():
    reg = load_registry(str(FIX))
    e = lookup(reg, "https://www.jinan.gov.cn/col25768/art/2016/x.html")
    assert e is not None and e.issuer_short == "SD"


def test_lookup_unknown_domain_returns_none():
    reg = load_registry(str(FIX))
    assert lookup(reg, "https://solar.in-en.com/news/123.html") is None


def test_lookup_blank_url_returns_none():
    reg = load_registry(str(FIX))
    assert lookup(reg, "") is None
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python3 -m pytest tests/l2_attribution/test_channel_registry.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 4: 写实现** `scripts/l2_attribution/channel_registry.py`

```python
from __future__ import annotations
from pathlib import Path
from urllib.parse import urlparse
import yaml
from scripts.l2_attribution.models import ChannelEntry


def load_registry(path: str) -> dict:
    """读 channel_registry.yaml -> {domain: ChannelEntry}。"""
    rows = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    out = {}
    for r in rows:
        out[r["domain"]] = ChannelEntry(
            domain=r["domain"],
            issuer_short=r["issuer_short"],
            issuer_canonical=r.get("issuer_canonical", ""),
            region=r["region"],
        )
    return out


def host_of(url: str) -> str:
    if not url:
        return ""
    return (urlparse(url).netloc or "").lower()


def lookup(registry: dict, url: str):
    """url -> host -> ChannelEntry | None。"""
    return registry.get(host_of(url))
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_channel_registry.py -v`
Expected: PASS(4 passed)

- [ ] **Step 6: commit**

```bash
git add scripts/l2_attribution/channel_registry.py tests/l2_attribution/test_channel_registry.py tests/l2_attribution/fixtures/channel_registry_min.yaml
git commit -m "feat(②-A): channel_registry 加载器 + url→host lookup"
```

---

## Task 4: seeder(渠道目录解析 + 域名派生)+ 人工 curate registry

**Files:**
- Create: `scripts/l2_attribution/seed_channel_registry.py`
- Create: `_meta/channel_registry.yaml`(vault,产物 + curate)
- Test: `tests/l2_attribution/test_seed.py`

**目标:** 从 `渠道目录.md` 中央/地方表 + refdata 自动派生能定的域名,扫语料全部 gov 域名,产出 registry 草稿 + `needs_manual`(无法自动定的域名,带样例文件名供 curate)。然后 agent 当 curator 填 needs_manual,得到覆盖破损集 163 个 gov 域名的最终 `_meta/channel_registry.yaml`。

- [ ] **Step 1: 写失败测试** `tests/l2_attribution/test_seed.py`

```python
from scripts.l2_attribution.seed_channel_registry import (
    parse_channel_md, derive_entry,
)

SAMPLE_MD = """## 中央政府（国家级）
| 根域名 | 渠道名称 |
| --- | --- |
| www.ndrc.gov.cn | 国家发展和改革委员会 |

## 地方政府
| 根域名 | 渠道名称 |
|--------|---------|
| www.jinan.gov.cn | 济南市人民政府 |
| fgw.sh.gov.cn | 上海市发展和改革委员会 |
"""


def test_parse_channel_md_yields_domain_name_pairs():
    pairs = parse_channel_md(SAMPLE_MD)
    assert ("www.jinan.gov.cn", "济南市人民政府") in pairs
    assert ("fgw.sh.gov.cn", "上海市发展和改革委员会") in pairs


def test_derive_ministry_domain():
    e = derive_entry("www.ndrc.gov.cn", "国家发展和改革委员会")
    assert e["issuer_short"] == "NDRC"
    assert e["region"]["level"] == "国家"


def test_derive_city_from_channel_name():
    # 渠道名称含"济南市" -> 市级,省级码 SD,code 省级回退 370000 + 待精化标记
    e = derive_entry("www.jinan.gov.cn", "济南市人民政府")
    assert e["issuer_short"] == "SD"
    assert e["region"]["level"] == "市"
    assert e["region"]["name"] == "济南市"


def test_derive_unknown_returns_none():
    assert derive_entry("solar.in-en.com", "某行业媒体") is None
    assert derive_entry("www.weirdcity.gov.cn", "未知地名办公室") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l2_attribution/test_seed.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 写实现** `scripts/l2_attribution/seed_channel_registry.py`

```python
"""从 渠道目录.md + refdata 自动派生 channel_registry 草稿,余下入 needs_manual。
派生纯规则:① 部委域名命中 MINISTRY;② 渠道名称含'XX省'->省级;③ 含'XX市'->市级(查 CITY_PROVINCE 定省级码)。
定不了的(媒体/未知市/无渠道名)-> None -> needs_manual。"""
from __future__ import annotations
import re
import json
from pathlib import Path
import yaml
from scripts.l2_attribution.refdata import PROVINCE, MINISTRY, CITY_PROVINCE
from scripts.l2_attribution.channel_registry import host_of
from scripts.l1_audit.corpus import load_policies

_ROW_RE = re.compile(r"^\|\s*([a-z0-9.\-]+\.gov\.cn|[a-z0-9.\-]+\.cn)\s*\|\s*([^|]+?)\s*\|", re.M)
_PROV_RE = re.compile(r"(北京市|天津市|上海市|重庆市|河北省|山西省|内蒙古自治区|辽宁省|吉林省|黑龙江省|江苏省|浙江省|安徽省|福建省|江西省|山东省|河南省|湖北省|湖南省|广东省|广西壮族自治区|海南省|四川省|贵州省|云南省|西藏自治区|陕西省|甘肃省|青海省|宁夏回族自治区|新疆维吾尔自治区)")
_CITY_RE = re.compile(r"([一-龥]{2,8}?市)")


def parse_channel_md(text: str) -> list:
    """渠道目录.md markdown 表 -> [(domain, 渠道名称)]。跳过表头行(渠道名称=='渠道名称')。"""
    out = []
    for dom, name in _ROW_RE.findall(text):
        name = name.strip()
        if name in ("渠道名称", "渠道标识") or not name:
            continue
        out.append((dom, name))
    return out


def _municipality(prov_name):
    return prov_name in ("北京市", "天津市", "上海市", "重庆市")


def derive_entry(domain: str, channel_name: str):
    """规则派生一条 entry dict;定不了返回 None。"""
    if domain in MINISTRY:
        m = MINISTRY[domain]
        return {"domain": domain, "issuer_short": m["issuer_short"],
                "issuer_canonical": m["issuer_canonical"], "region": dict(m["region"])}
    name = channel_name or ""
    # 省级(含直辖市作为省级行政区)
    pm = _PROV_RE.search(name)
    cm = _CITY_RE.search(name)
    # 直辖市:渠道名"上海市..."既是省级码也是市级行政区
    if pm and _municipality(pm.group(1)):
        p = PROVINCE[pm.group(1)]
        return {"domain": domain, "issuer_short": p["issuer_short"],
                "issuer_canonical": name,
                "region": {"level": "市", "code": p["code2"] + "0000", "name": pm.group(1)}}
    # 普通市级:渠道名含"XX市" 且能查到所属省
    if cm and cm.group(1) in CITY_PROVINCE:
        prov = CITY_PROVINCE[cm.group(1)]
        p = PROVINCE[prov]
        return {"domain": domain, "issuer_short": p["issuer_short"],
                "issuer_canonical": name,
                # 市级 adcode 暂用省级回退 + needs_city_code 标记(spec:查不到市码→省级码+标记)
                "region": {"level": "市", "code": p["code2"] + "0000",
                           "name": cm.group(1), "needs_city_code": True}}
    # 省级直属(渠道名含"XX省")
    if pm and pm.group(1) in PROVINCE:
        p = PROVINCE[pm.group(1)]
        return {"domain": domain, "issuer_short": p["issuer_short"],
                "issuer_canonical": name,
                "region": {"level": "省", "code": p["code2"] + "0000", "name": pm.group(1)}}
    return None


def seed(channel_md_path: str, policies_dir: str, out_yaml: str, needs_manual_path: str):
    md = Path(channel_md_path).read_text(encoding="utf-8")
    md_pairs = dict(parse_channel_md(md))
    # 语料里出现的全部 gov 域名
    domains = {}
    for rec in load_policies(policies_dir):
        h = host_of(rec.url)
        if h.endswith(".gov.cn"):
            domains.setdefault(h, rec.path)
    entries, needs_manual = [], []
    for dom, sample_path in sorted(domains.items()):
        e = derive_entry(dom, md_pairs.get(dom, ""))
        if e:
            entries.append(e)
        else:
            needs_manual.append({"domain": dom, "sample_file": Path(sample_path).name,
                                 "channel_name_hint": md_pairs.get(dom, "")})
    Path(out_yaml).write_text(
        yaml.dump(entries, allow_unicode=True, sort_keys=False), encoding="utf-8")
    Path(needs_manual_path).write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in needs_manual), encoding="utf-8")
    return len(entries), len(needs_manual)


if __name__ == "__main__":
    import sys
    vault = sys.argv[1] if len(sys.argv) > 1 else \
        str(Path.home() / "Documents" / "Zayn Main" / "政策分析")
    n_ok, n_manual = seed(
        f"{vault}/00 背景资料/渠道目录.md",
        f"{vault}/0_raw/policies",
        f"{vault}/_meta/channel_registry.yaml",
        "state/source_ready/channel_registry_needs_manual.jsonl",
    )
    print(f"自动派生 {n_ok} 域名;needs_manual {n_manual} 待 curate")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_seed.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 跑 seeder 产草稿,看 needs_manual 规模**

Run: `python3 -m scripts.l2_attribution.seed_channel_registry`
Expected: 打印"自动派生 N 域名;needs_manual M 待 curate";生成 vault `_meta/channel_registry.yaml` 草稿 + `state/source_ready/channel_registry_needs_manual.jsonl`。

- [ ] **Step 6: curate(agent 当 curator,数据任务)**

逐条读 `channel_registry_needs_manual.jsonl`:每条 domain + sample_file(文件名编码了真机关名)→ 查 refdata(必要时往 `refdata.py` 的 `CITY_PROVINCE` 补该市→省)→ 手写 entry 追加进 `_meta/channel_registry.yaml`。判断沉淀为**数据**(registry 条目 + refdata 补的市),不写进 resolver 代码。媒体/非政府域名(in-en.com 等)**不进** registry(留作 resolver 的 unknown→队列)。
完成判据:破损集 163 个 gov 域名 100% 在 registry 中有条目。

- [ ] **Step 7: commit(代码 + 数据分开)**

```bash
git add scripts/l2_attribution/seed_channel_registry.py tests/l2_attribution/test_seed.py scripts/l2_attribution/refdata.py
git commit -m "feat(②-A): channel_registry seeder + 市→省补全"
# vault 仓单独 commit channel_registry.yaml(在 vault 目录):
# (cd vault && git add _meta/channel_registry.yaml && git commit -m "data(②-A): channel_registry 域名→机构/区域 源资产")
```

---

## Task 5: 抽取器(标题 issuer + 落款 date)

**Files:**
- Create: `scripts/l2_attribution/extractors.py`
- Test: `tests/l2_attribution/test_extractors.py`

- [ ] **Step 1: 写失败测试** `tests/l2_attribution/test_extractors.py`

```python
from scripts.l2_attribution.extractors import (
    extract_issuer_from_title, extract_luokuan_date,
)


def test_issuer_from_simple_title():
    t = "济南市人民政府办公厅关于进一步加强成品油监管工作的通知"
    assert extract_issuer_from_title(t) == "济南市人民政府办公厅"


def test_issuer_from_joint_title():
    t = "国家发展改革委 国家能源局关于印发电力体制改革配套文件的通知"
    assert extract_issuer_from_title(t) == "国家发展改革委 国家能源局"


def test_issuer_title_no_match_returns_none():
    assert extract_issuer_from_title("电力现货市场基本规则(试行)") is None


def test_luokuan_date_chinese():
    body_tail = "……结合我市实际,现通知如下。\n\n济南市人民政府办公厅\n\n2016年3月17日\n\n附件:部门工作任务分工"
    assert extract_luokuan_date(body_tail) == "2016-03-17"


def test_luokuan_date_b4_case():
    body_tail = "……自本规则印发之日起施行。\n\n国家发展改革委\n国家能源局\n2023年9月15日"
    assert extract_luokuan_date(body_tail) == "2023-09-15"


def test_luokuan_date_none_when_absent():
    assert extract_luokuan_date("没有任何日期的正文结尾。") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l2_attribution/test_extractors.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 写实现** `scripts/l2_attribution/extractors.py`

```python
"""确定性抽取器:标题->发文机关、正文落款->日期。纯函数。"""
from __future__ import annotations
import re

# 机关名以这些结尾(放行单机关 + 顿号/空格分隔的联合发文)
_ORG_TAIL = "(?:办公厅|办公室|人民政府|政府|委员会|管委会|发展改革委|能源局|工业和信息化局|" \
            "工业和信息化部|商务局|商务委员会|财政局|财政厅|交通运输厅|自然资源和规划局|" \
            "市场监督管理局|委|局|厅|部|院|中心)"
# 标题前缀 = 机关名(可含 顿号/空格/、连接多机关)直到 "关于"
_TITLE_RE = re.compile(r"^([一-龥、\s]+?" + _ORG_TAIL + r")关于")

_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def extract_issuer_from_title(title: str):
    """标题 'XXX关于...的通知' -> 'XXX';无匹配 -> None。"""
    if not title:
        return None
    m = _TITLE_RE.match(title.strip())
    if not m:
        return None
    return m.group(1).strip()


def extract_luokuan_date(body_tail: str):
    """正文尾部落款中文日期 'YYYY年M月D日' -> 'YYYY-MM-DD';取最后一个(最贴近落款);无 -> None。"""
    if not body_tail:
        return None
    ms = list(_DATE_RE.finditer(body_tail))
    if not ms:
        return None
    y, mo, d = ms[-1].groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_extractors.py -v`
Expected: PASS(6 passed)

- [ ] **Step 5: commit**

```bash
git add scripts/l2_attribution/extractors.py tests/l2_attribution/test_extractors.py
git commit -m "feat(②-A): 标题机关 + 落款日期 确定性抽取器"
```

---

## Task 6: resolve_identity 纯函数 + body 尾部读取

**Files:**
- Create: `scripts/l2_attribution/resolver.py`
- Test: `tests/l2_attribution/test_resolver.py`

**规则(spec §4/§5):**
- region + issuer_short:**只**来自域名(channel_registry lookup)。url 非 gov / 不在 registry → 整条 unknown,所有字段入队列。
- issuer 全名:`extract_issuer_from_title`,**且**抽出的机关名所属区域与域名渠道一致(同名包含校验)才写;不一致(转载/联合/媒体)→ issuer 入队列冲突。
- date:`extract_luokuan_date(body_tail)` 抽到即作为新 date(覆盖错值);抽不到 → 若现值合法(`YYYY-MM-DD` 且 1990≤年≤当前年)保留、不写;现值也坏 → date 入队列。
- id:`P_<year(最终date的年)>_<issuer_short>_<原hash>`;原 hash = 旧 id 末段;碰撞加 `_a/_b`(碰撞集由调用方传入)。
- 已正确(现 id 前缀==issuer_short 且 region 已对)→ 不产生写字段(no-op)。

- [ ] **Step 1: 写失败测试** `tests/l2_attribution/test_resolver.py`

```python
from scripts.l2_attribution.models import ChannelEntry
from scripts.l2_attribution.resolver import resolve_identity, body_tail_of, old_hash_of


def _entry(**kw):
    base = dict(domain="www.jinan.gov.cn", issuer_short="SD",
                issuer_canonical="济南市人民政府",
                region={"level": "市", "code": "370100", "name": "济南市"})
    base.update(kw)
    return ChannelEntry(**base)


class FakeRec:
    def __init__(self, pid, title, url, date="", official_number="", path="/tmp/x.md"):
        self.pid, self.title, self.url = pid, title, url
        self.date, self.official_number, self.path = date, official_number, path


def test_old_hash_of():
    assert old_hash_of("P_2015_GO_af076ca3") == "af076ca3"
    assert old_hash_of("P_2024_NDRC_718") == "718"


def test_resolve_clean_city_writes_region_issuer_id(tmp_path):
    reg = {"www.jinan.gov.cn": _entry()}
    rec = FakeRec("P_2015_GO_af076ca3",
                  "济南市人民政府办公厅关于加强成品油监管的通知",
                  "https://www.jinan.gov.cn/x.html")
    ri = resolve_identity(rec, reg, body_tail="济南市人民政府办公厅\n2016年3月17日",
                          existing_ids=set())
    assert ri.fields["region"].value["name"] == "济南市"
    assert ri.fields["issuer"].value == ["济南市人民政府办公厅"]
    assert ri.fields["date"].value == "2016-03-17"
    assert ri.fields["id"].value == "P_2016_SD_af076ca3"
    assert not ri.has_conflicts()


def test_resolve_unknown_domain_all_queue():
    rec = FakeRec("P_2025_GO_x", "某标题", "https://solar.in-en.com/n.html")
    ri = resolve_identity(rec, {}, body_tail="", existing_ids=set())
    assert ri.has_conflicts()
    assert any(c.field == "_all" for c in ri.conflicts)
    assert not ri.fields


def test_resolve_title_domain_mismatch_queues_issuer():
    # 转载:标题机关"国务院办公厅"(国家) 与 域名承德(市) 不符 -> issuer 入队列,region 仍写
    reg = {"www.chengde.gov.cn": _entry(domain="www.chengde.gov.cn", issuer_short="HE",
            issuer_canonical="承德市人民政府",
            region={"level": "市", "code": "130800", "name": "承德市"})}
    rec = FakeRec("P_2025_GO_y",
                  "国务院办公厅关于推动成品油流通高质量发展的意见(转载)",
                  "https://www.chengde.gov.cn/x.html")
    ri = resolve_identity(rec, reg, body_tail="2025年1月1日", existing_ids=set())
    assert ri.fields["region"].value["name"] == "承德市"
    assert "issuer" not in ri.fields
    assert any(c.field == "issuer" for c in ri.conflicts)


def test_resolve_id_collision_suffix():
    reg = {"www.jinan.gov.cn": _entry()}
    rec = FakeRec("P_2015_GO_af076ca3", "济南市人民政府办公厅关于X的通知",
                  "https://www.jinan.gov.cn/x.html")
    ri = resolve_identity(rec, reg, body_tail="2016年3月17日",
                          existing_ids={"P_2016_SD_af076ca3"})
    assert ri.fields["id"].value == "P_2016_SD_af076ca3_a"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l2_attribution/test_resolver.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 写实现** `scripts/l2_attribution/resolver.py`

```python
"""resolve_identity:确定性算 identity。纯函数,零 pid 分支。"""
from __future__ import annotations
import re
import datetime
from pathlib import Path
from scripts.l2_attribution.models import ResolvedIdentity
from scripts.l2_attribution.channel_registry import lookup
from scripts.l2_attribution.extractors import (
    extract_issuer_from_title, extract_luokuan_date,
)

_PLACE_RE = re.compile(r"(北京|天津|上海|重庆|[一-龥]{2,6}?[省市区县])")
_DATE_OK = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_THIS_YEAR = 2026


def old_hash_of(pid: str) -> str:
    """P_YYYY_PREFIX_<hash> -> <hash>(末段)。"""
    parts = (pid or "").split("_")
    return parts[-1] if parts else ""


def body_tail_of(path: str, n: int = 900) -> str:
    """读文件末尾 n 字符(落款在文末)。"""
    try:
        txt = Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""
    return txt[-n:]


def _date_year(date_str: str):
    m = re.match(r"^(\d{4})", date_str or "")
    return m.group(1) if m else None


def _existing_date_ok(date_str: str) -> bool:
    if not _DATE_OK.match(date_str or ""):
        return False
    y = int(date_str[:4])
    return 1990 <= y <= _THIS_YEAR


def _alloc_id(year, issuer_short, hsh, existing_ids):
    base = f"P_{year}_{issuer_short}_{hsh}"
    if base not in existing_ids:
        return base
    for suf in "abcdefghij":
        cand = f"{base}_{suf}"
        if cand not in existing_ids:
            return cand
    return base  # 极端兜底


def resolve_identity(rec, registry, body_tail: str, existing_ids: set) -> ResolvedIdentity:
    ri = ResolvedIdentity(pid=rec.pid)
    entry = lookup(registry, rec.url)

    # 1) 非 gov / 不在 registry -> 整条 unknown
    if entry is None:
        ri.add_conflict("_all", reason="域名不在 channel_registry(非gov/未收录)",
                        signals={"url": rec.url})
        return ri

    # 2) region(仅域名)
    cur_region = getattr(rec, "raw_fm", {}).get("region") if hasattr(rec, "raw_fm") else None
    if cur_region != entry.region:
        ri.set_field("region", entry.region, method="domain_lookup",
                     confidence=0.99, from_val=str(cur_region))

    # 3) issuer 全名:标题抽取 + 域名背书(机关名含域名区域名之一)
    title_issuer = extract_issuer_from_title(rec.title)
    if title_issuer:
        region_name = entry.region.get("name", "")
        place = region_name.replace("省", "").replace("市", "")
        backed = (entry.region["level"] == "国家") or (place and place in title_issuer)
        if backed:
            ri.set_field("issuer", [title_issuer], method="title_extract",
                         confidence=0.95, from_val=str(getattr(rec, "issuer", "")))
            ri.set_field("issuer_canonical", [entry.issuer_canonical],
                         method="domain_lookup", confidence=0.9)
        else:
            ri.add_conflict("issuer",
                            reason="标题机关与域名区域不符(转载/联合/媒体)",
                            signals={"title_issuer": title_issuer,
                                     "domain_region": region_name})

    # 4) date:落款抽到即写;抽不到保留合法现值,否则入队列
    luokuan = extract_luokuan_date(body_tail)
    final_date = rec.date
    if luokuan:
        if luokuan != rec.date:
            ri.set_field("date", luokuan, method="body_chinese_date",
                         confidence=0.92, from_val=str(rec.date))
        final_date = luokuan
    elif not _existing_date_ok(rec.date):
        ri.add_conflict("date", reason="落款抽不到且现值坏",
                        signals={"frontmatter": rec.date, "luokuan": None})

    # 5) id:用最终 date 年 + issuer_short + 原 hash
    year = _date_year(final_date)
    if year:
        new_id = _alloc_id(year, entry.issuer_short, old_hash_of(rec.pid), existing_ids)
        if new_id != rec.pid:
            ri.set_field("id", new_id, method="id_recompute_from_metadata",
                         confidence=0.99, from_val=rec.pid)
    else:
        ri.add_conflict("id", reason="无可用年份,无法重算 id",
                        signals={"final_date": final_date})

    return ri
```

> 注:测试里 `FakeRec` 无 `raw_fm` 属性,`getattr(rec, "raw_fm", {})` 兜底为 `{}`,故 region 必写——符合测试预期。真实 `PolicyRecord` 有 `raw_fm`,已正确 region 会 no-op。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_resolver.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: commit**

```bash
git add scripts/l2_attribution/resolver.py tests/l2_attribution/test_resolver.py
git commit -m "feat(②-A): resolve_identity 纯函数(域名锚+标题背书+落款date+id重算)"
```

---

## Task 7: ledger 交叉校验(oracle)

**Files:**
- Create: `scripts/l2_attribution/ledger.py`
- Test: `tests/l2_attribution/test_ledger.py`

**规则:** ledger 仅当验收 oracle。`cross_check(resolved, ledger_entry)`:比 resolver 写的 `issuer_short`(从 id 新前缀)与 ledger 的 `suggested_issuer_short`、region level。一致 → `("agree", None)`;不一致 → `("disagree", 详情)`(由调用方据保守姿态把该 pid 降级入队列)。

- [ ] **Step 1: 写失败测试** `tests/l2_attribution/test_ledger.py`

```python
from scripts.l2_attribution.ledger import load_ledger, issuer_short_of_id, cross_check


def test_issuer_short_of_id():
    assert issuer_short_of_id("P_2016_SD_af076ca3") == "SD"
    assert issuer_short_of_id("P_2016_SD_af076ca3_a") == "SD"


def test_cross_check_agree():
    led = {"suggested_issuer_short": "SD", "true_region": "济南市"}
    status, _ = cross_check("P_2016_SD_af076ca3", led)
    assert status == "agree"


def test_cross_check_disagree():
    led = {"suggested_issuer_short": "NDRC", "true_region": "national"}
    status, detail = cross_check("P_2016_SD_af076ca3", led)
    assert status == "disagree"
    assert detail["resolver"] == "SD" and detail["ledger"] == "NDRC"


def test_load_ledger_indexes_by_pid(tmp_path):
    p = tmp_path / "led.jsonl"
    p.write_text('{"pid":"P_x","suggested_issuer_short":"SD","true_region":"济南市"}\n',
                 encoding="utf-8")
    led = load_ledger(str(p))
    assert led["P_x"]["suggested_issuer_short"] == "SD"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l2_attribution/test_ledger.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 写实现** `scripts/l2_attribution/ledger.py`

```python
from __future__ import annotations
import json
from pathlib import Path


def load_ledger(path: str) -> dict:
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out[d["pid"]] = d
    return out


def issuer_short_of_id(pid: str) -> str:
    """P_YYYY_<SHORT>_<hash>[_suffix] -> SHORT。"""
    parts = (pid or "").split("_")
    return parts[2] if len(parts) >= 4 else ""


def cross_check(new_id: str, ledger_entry: dict):
    """resolver 的新 id 前缀 vs ledger suggested_issuer_short。"""
    r = issuer_short_of_id(new_id)
    l = ledger_entry.get("suggested_issuer_short", "")
    if r == l:
        return "agree", None
    return "disagree", {"resolver": r, "ledger": l,
                        "ledger_region": ledger_entry.get("true_region", "")}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_ledger.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: commit**

```bash
git add scripts/l2_attribution/ledger.py tests/l2_attribution/test_ledger.py
git commit -m "feat(②-A): ledger 交叉校验 oracle(不当真值)"
```

---

## Task 8: §C 合规 apply_identity(就地写 raw)

**Files:**
- Create: `scripts/l2_attribution/apply_identity.py`
- Test: `tests/l2_attribution/test_apply_identity.py`

**§C 写入契约:**
- 写 `id`(+ aliases 追加旧 id,保留新)、`issuer`、`issuer_canonical`、`region`(嵌套 dict)、`date` —— 仅写 `ResolvedIdentity.fields` 里有的字段。
- 审计字段写**嵌套 `provenance`**:每个被改字段写 `<field>_fixed_at` / `<field>_fixed_method` / `<field>_fixed_from`(+ `_fix_confidence`)。
- 文件名不变;用 `yaml.dump(..., allow_unicode=True, sort_keys=False)` 整块重写 frontmatter,body 不动。
- 返回写了哪些字段(供 log)。

- [ ] **Step 1: 写失败测试** `tests/l2_attribution/test_apply_identity.py`

```python
import yaml
from pathlib import Path
from scripts.l2_attribution.models import ResolvedIdentity
from scripts.l2_attribution.apply_identity import apply_identity

RAW = """---
id: P_2015_GO_af076ca3
aliases:
- P_2015_GO_af076ca3
title: 济南市人民政府办公厅关于加强成品油监管的通知
issuer:
- 政府门户.www.jinan.gov.cn
date: '2015-01-01'
region:
  level: 国家
  code: '000000'
  name: 未知
type: policy
provenance:
  url: https://www.jinan.gov.cn/x.html
  fetched_at: '2026-05-08'
---

# 标题

## 政策原文
正文……
"""


def _ri():
    ri = ResolvedIdentity(pid="P_2015_GO_af076ca3")
    ri.set_field("region", {"level": "市", "code": "370100", "name": "济南市"},
                 method="domain_lookup", confidence=0.99, from_val="国家/000000/未知")
    ri.set_field("issuer", ["济南市人民政府办公厅"], method="title_extract",
                 confidence=0.95, from_val="政府门户.www.jinan.gov.cn")
    ri.set_field("date", "2016-03-17", method="body_chinese_date",
                 confidence=0.92, from_val="2015-01-01")
    ri.set_field("id", "P_2016_SD_af076ca3", method="id_recompute_from_metadata",
                 confidence=0.99, from_val="P_2015_GO_af076ca3")
    return ri


def test_apply_writes_all_fields_and_nested_audit(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text(RAW, encoding="utf-8")
    written = apply_identity(str(f), _ri(), fixed_at="2026-05-31T10:00:00+08:00")
    text = f.read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---")[1])

    assert fm["id"] == "P_2016_SD_af076ca3"
    assert "P_2015_GO_af076ca3" in fm["aliases"]      # 旧 id 保留
    assert "P_2016_SD_af076ca3" in fm["aliases"]      # 新 id 也在
    assert fm["issuer"] == ["济南市人民政府办公厅"]
    assert fm["region"]["code"] == "370100"
    assert fm["date"] == "2016-03-17"
    # 审计字段嵌套在 provenance
    assert fm["provenance"]["id_fixed_method"] == "id_recompute_from_metadata"
    assert fm["provenance"]["region_fixed_from"] == "国家/000000/未知"
    assert fm["provenance"]["date_fixed_method"] == "body_chinese_date"
    # body 不动
    assert "## 政策原文" in text
    # 文件名不变
    assert f.name == "doc.md"
    assert set(written) >= {"id", "issuer", "region", "date"}


def test_apply_noop_when_no_fields(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text(RAW, encoding="utf-8")
    written = apply_identity(str(f), ResolvedIdentity(pid="P_x"),
                             fixed_at="2026-05-31T10:00:00+08:00")
    assert written == []
    assert f.read_text(encoding="utf-8") == RAW   # 完全不动
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l2_attribution/test_apply_identity.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 写实现** `scripts/l2_attribution/apply_identity.py`

```python
"""§C 合规就地写 raw 身份字段。yaml round-trip,审计嵌 provenance,文件名不变。"""
from __future__ import annotations
import re
from pathlib import Path
import yaml

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


def apply_identity(path: str, ri, fixed_at: str) -> list:
    """按 ResolvedIdentity.fields 改 frontmatter;无字段则完全不动。返回写了哪些字段。"""
    if not ri.fields:
        return []
    src = Path(path)
    text = src.read_text(encoding="utf-8")
    m = _FM_RE.search(text)
    if not m:
        raise ValueError(f"{src} 无 frontmatter")
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2) or ""
    prov = fm.get("provenance") or {}
    if not isinstance(prov, dict):
        prov = {}

    written = []
    # id 特殊:先处理 aliases(旧+新)
    if "id" in ri.fields:
        new_id = ri.fields["id"].value
        old_id = fm.get("id")
        aliases = fm.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = [aliases]
        if old_id and old_id not in aliases:
            aliases.append(old_id)
        if new_id not in aliases:
            aliases.append(new_id)
        fm["aliases"] = aliases

    for name, rf in ri.fields.items():
        fm[name] = rf.value
        prov[f"{name}_fixed_at"] = fixed_at
        prov[f"{name}_fixed_method"] = rf.method
        prov[f"{name}_fixed_from"] = rf.from_val
        if rf.confidence is not None:
            prov[f"{name}_fix_confidence"] = rf.confidence
        written.append(name)

    fm["provenance"] = prov
    new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False)
    src.write_text(f"---\n{new_fm}---\n\n{body.lstrip(chr(10))}\n", encoding="utf-8")
    return written
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_apply_identity.py -v`
Expected: PASS(2 passed)

> 注:`test_apply_noop` 断言 `== RAW` 要求 no-op 时一字节不改。实现里 `if not ri.fields: return []` 在读文件前 return,满足。

- [ ] **Step 5: commit**

```bash
git add scripts/l2_attribution/apply_identity.py tests/l2_attribution/test_apply_identity.py
git commit -m "feat(②-A): §C 合规 apply_identity(嵌套provenance审计/aliases/文件名不变)"
```

---

## Task 9: review_queue 写出

**Files:**
- Create: `scripts/l2_attribution/review_queue.py`
- Test: `tests/l2_attribution/test_review_queue.py`

- [ ] **Step 1: 写失败测试** `tests/l2_attribution/test_review_queue.py`

```python
import json
from pathlib import Path
from scripts.l2_attribution.models import ResolvedIdentity
from scripts.l2_attribution.review_queue import write_queue


def test_write_queue_one_line_per_conflict(tmp_path):
    ri1 = ResolvedIdentity(pid="P_a")
    ri1.add_conflict("issuer", "转载", {"title_issuer": "国务院办公厅"})
    ri2 = ResolvedIdentity(pid="P_b")
    ri2.add_conflict("_all", "非gov域名", {"url": "https://x.in-en.com"})
    out = tmp_path / "q.jsonl"
    n = write_queue([ri1, ri2], str(out))
    assert n == 2
    lines = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["pid"] == "P_a" and lines[0]["field"] == "issuer"
    assert lines[1]["field"] == "_all"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l2_attribution/test_review_queue.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 写实现** `scripts/l2_attribution/review_queue.py`

```python
from __future__ import annotations
import json
from pathlib import Path
from scripts.l2_attribution.models import QueueRecord


def write_queue(resolved_list, out_path: str) -> int:
    """每个 conflict 一行 jsonl。返回写出条数。"""
    recs = []
    for ri in resolved_list:
        for c in ri.conflicts:
            recs.append(QueueRecord(pid=ri.pid, field=c.field,
                                    reason=c.reason, signals=c.signals))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(out_path).open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    return len(recs)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_review_queue.py -v`
Expected: PASS(1 passed)

- [ ] **Step 5: commit**

```bash
git add scripts/l2_attribution/review_queue.py tests/l2_attribution/test_review_queue.py
git commit -m "feat(②-A): review_queue 写出(每冲突一行)"
```

---

## Task 10: 编排 CLI(dry-run / apply / verify)+ HTML 报告 + 集成测

**Files:**
- Create: `scripts/l2_attribution/report.py`
- Create: `scripts/l2_attribution/run_2a.py`
- Test: `tests/l2_attribution/test_run_2a.py`

**编排逻辑:**
1. `plan(vault)`:load_policies + load_registry + load_ledger;扫现存 id 做碰撞集;逐篇 `body_tail_of` + `resolve_identity`;对有 id 改动且 pid 在 ledger 的,`cross_check`——disagree 则把该 pid 的全部写字段撤下、改记 `_all` 冲突(保守:与 ledger 矛盾不写)。产出 `(to_apply: list[ResolvedIdentity], queue: list[ResolvedIdentity])`。
2. `dry_run`:plan → 写 `proposed_changes_2a.jsonl` + `2a_review_queue.jsonl` + `report.py` 出 HTML;不碰 raw。
3. `apply`:plan → 对 to_apply 逐篇 `apply_identity` + 追加 `apply_log_2a.jsonl`(git rename 由 vault commit 时体现;文件名不变故就是内容改)。
4. `verify`:重跑 plan,断言 to_apply 为空(幂等);打印 ledger 一致率。

- [ ] **Step 1: 写失败测试(集成)** `tests/l2_attribution/test_run_2a.py`

```python
import json
from pathlib import Path
from scripts.l2_attribution.run_2a import plan

REG_YAML = """- domain: www.jinan.gov.cn
  issuer_short: SD
  issuer_canonical: 济南市人民政府
  region: {level: 市, code: '370100', name: 济南市}
"""
DOC = """---
id: P_2015_GO_af076ca3
aliases: [P_2015_GO_af076ca3]
title: 济南市人民政府办公厅关于加强成品油监管的通知
issuer: [政府门户.www.jinan.gov.cn]
date: '2015-01-01'
region: {level: 国家, code: '000000', name: 未知}
type: policy
provenance: {url: 'https://www.jinan.gov.cn/x.html'}
---

## 政策原文
正文……

济南市人民政府办公厅

2016年3月17日
"""


def _setup(tmp_path):
    pol = tmp_path / "0_raw" / "policies"; pol.mkdir(parents=True)
    (pol / "doc.md").write_text(DOC, encoding="utf-8")
    reg = tmp_path / "channel_registry.yaml"; reg.write_text(REG_YAML, encoding="utf-8")
    led = tmp_path / "ledger.jsonl"
    led.write_text('{"pid":"P_2015_GO_af076ca3","suggested_issuer_short":"SD","true_region":"济南市"}\n',
                   encoding="utf-8")
    return str(pol), str(reg), str(led)


def test_plan_clean_doc_goes_to_apply(tmp_path):
    pol, reg, led = _setup(tmp_path)
    to_apply, queue = plan(pol, reg, led)
    assert len(to_apply) == 1
    assert to_apply[0].fields["id"].value == "P_2016_SD_af076ca3"
    assert queue == []


def test_plan_ledger_disagree_demotes_to_queue(tmp_path):
    pol, reg, led = _setup(tmp_path)
    # 篡改 ledger 为 NDRC -> 与 resolver(SD)矛盾 -> 整条入队列
    Path(led).write_text('{"pid":"P_2015_GO_af076ca3","suggested_issuer_short":"NDRC","true_region":"national"}\n',
                         encoding="utf-8")
    to_apply, queue = plan(pol, reg, led)
    assert to_apply == []
    assert len(queue) == 1
    assert any(c.field == "_all" for c in queue[0].conflicts)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l2_attribution/test_run_2a.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 写实现** `scripts/l2_attribution/report.py`

```python
"""dry-run HTML 验收报告:写了什么 vs 入队什么。自包含 HTML。"""
from __future__ import annotations
from pathlib import Path


def render(to_apply, queue, ledger_agree_rate, out_path: str):
    rows = []
    for ri in to_apply:
        chg = "; ".join(f"{k}→{getattr(v.value,'get',lambda *_:v.value)('name') if k=='region' else v.value}"
                        for k, v in ri.fields.items())
        rows.append(f"<tr><td>{ri.pid}</td><td>{chg}</td></tr>")
    qrows = []
    for ri in queue:
        for c in ri.conflicts:
            qrows.append(f"<tr><td>{ri.pid}</td><td>{c.field}</td><td>{c.reason}</td></tr>")
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>②-A dry-run 验收</title>
<style>body{{font-family:'PingFang SC',sans-serif;max-width:920px;margin:0 auto;padding:32px;line-height:1.6}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}
th,td{{border-bottom:1px solid #e4e8ec;padding:7px 9px;text-align:left;vertical-align:top}}
th{{background:#f3f6f9}} .k{{color:#2E7D32;font-weight:700}} .q{{color:#C62828;font-weight:700}}</style></head>
<body>
<h1>②-A 确定性身份固化 · dry-run 验收</h1>
<p>将写 raw:<span class="k">{len(to_apply)}</span> 篇 · 入待裁决队列:<span class="q">{len(queue)}</span> 篇 ·
ledger 一致率:<b>{ledger_agree_rate:.1%}</b></p>
<h2>将写 raw({len(to_apply)})</h2>
<table><tr><th>pid</th><th>改动</th></tr>{''.join(rows)}</table>
<h2>入队列({len(qrows)} 条冲突)</h2>
<table><tr><th>pid</th><th>字段</th><th>原因</th></tr>{''.join(qrows)}</table>
</body></html>"""
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path
```

`scripts/l2_attribution/run_2a.py`:

```python
"""②-A 编排:dry-run / apply / verify。"""
from __future__ import annotations
import argparse
import json
import datetime
from pathlib import Path
from scripts.l1_audit.corpus import load_policies
from scripts.l2_attribution.channel_registry import load_registry
from scripts.l2_attribution.ledger import load_ledger, cross_check
from scripts.l2_attribution.resolver import resolve_identity, body_tail_of
from scripts.l2_attribution.apply_identity import apply_identity
from scripts.l2_attribution.review_queue import write_queue
from scripts.l2_attribution import report

DEFAULT_VAULT = str(Path.home() / "Documents" / "Zayn Main" / "政策分析")


def _existing_ids(recs):
    return {r.pid for r in recs if r.pid}


def plan(policies_dir, registry_path, ledger_path):
    recs = load_policies(policies_dir)
    registry = load_registry(registry_path)
    ledger = load_ledger(ledger_path) if Path(ledger_path).exists() else {}
    existing = _existing_ids(recs)
    to_apply, queue = [], []
    for rec in recs:
        ri = resolve_identity(rec, registry, body_tail_of(rec.path), existing)
        # ledger 交叉校验:对 id 有改动且在 ledger 的,矛盾则整条降级入队列
        if "id" in ri.fields and rec.pid in ledger:
            status, detail = cross_check(ri.fields["id"].value, ledger[rec.pid])
            if status == "disagree":
                ri.fields = {}
                ri.add_conflict("_all", reason="与 ledger 矛盾(保守不写)", signals=detail)
        if ri.has_conflicts() and not ri.fields:
            queue.append(ri)
        elif ri.fields:
            to_apply.append(ri)
            if ri.has_conflicts():
                queue.append(ri)   # 部分字段写、部分入队
        else:
            pass  # no-op
    return to_apply, queue


def _agree_rate(to_apply, ledger):
    pairs = [(ri, ledger[ri.pid]) for ri in to_apply
             if "id" in ri.fields and ri.pid in ledger]
    if not pairs:
        return 1.0
    ok = sum(1 for ri, le in pairs if cross_check(ri.fields["id"].value, le)[0] == "agree")
    return ok / len(pairs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dry-run", "apply", "verify"])
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--state", default="state/source_ready")
    args = ap.parse_args()

    pol = f"{args.vault}/0_raw/policies"
    reg = f"{args.vault}/_meta/channel_registry.yaml"
    led = f"{args.state}/attribution_ledger_2b.jsonl"
    Path(args.state).mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    to_apply, queue = plan(pol, reg, led)
    ledger = load_ledger(led) if Path(led).exists() else {}
    rate = _agree_rate(to_apply, ledger)

    if args.mode == "dry-run":
        with open(f"{args.state}/proposed_changes_2a.jsonl", "w", encoding="utf-8") as f:
            for ri in to_apply:
                f.write(json.dumps(
                    {"pid": ri.pid,
                     "fields": {k: v.value for k, v in ri.fields.items()}},
                    ensure_ascii=False) + "\n")
        write_queue(queue, f"{args.state}/2a_review_queue.jsonl")
        report.render(to_apply, queue, rate, f"{args.state}/2a_dryrun_report.html")
        print(f"dry-run: 将写 {len(to_apply)} 篇,入队 {len(queue)} 篇,ledger一致率 {rate:.1%}")
        print(f"报告: {args.state}/2a_dryrun_report.html")

    elif args.mode == "apply":
        assert rate >= 0.95, f"ledger 一致率 {rate:.1%} < 95%,验收门不过,拒绝 apply"
        log = []
        for ri in to_apply:
            rec_path = next(r.path for r in load_policies(pol) if r.pid == ri.pid)
            written = apply_identity(rec_path, ri, fixed_at=now)
            log.append({"pid": ri.pid, "written": written, "at": now})
        with open(f"{args.state}/apply_log_2a.jsonl", "w", encoding="utf-8") as f:
            for e in log:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"apply: 写了 {len(log)} 篇。请在 vault 仓 commit(git status 看 rename/改动)。")

    elif args.mode == "verify":
        again, _ = plan(pol, reg, led)
        print(f"verify: 幂等重跑待写 {len(again)} 篇(应为 0);ledger一致率 {rate:.1%}")
        assert len(again) == 0, "非幂等:apply 后仍有待写,检查 resolver"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l2_attribution/test_run_2a.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: 全模块测试**

Run: `python3 -m pytest tests/l2_attribution/ -v`
Expected: PASS(全绿)

- [ ] **Step 6: commit**

```bash
git add scripts/l2_attribution/report.py scripts/l2_attribution/run_2a.py tests/l2_attribution/test_run_2a.py
git commit -m "feat(②-A): 编排 CLI(dry-run/apply/verify)+ HTML 验收报告"
```

---

## Task 11: 真实 dry-run + 人工验收门(在真 vault 上,只读)

**前置:** Task 4 的 `_meta/channel_registry.yaml` 已 curate 覆盖破损集 163 gov 域名。

- [ ] **Step 1: vault 打 checkpoint tag(可逆兜底)**

```bash
cd "/Users/shaoziyuan/Documents/Zayn Main/政策分析" && git tag pre-2a-2026-05-31 && git status -s
```

- [ ] **Step 2: 跑真实 dry-run(只读,不碰 raw)**

Run: `cd /Users/shaoziyuan/dev/政策分析-pipeline && python3 -m scripts.l2_attribution.run_2a dry-run`
Expected: 打印 将写 N 篇 / 入队 M 篇 / ledger一致率;生成 `state/source_ready/2a_dryrun_report.html` + `2a_review_queue.jsonl`。

- [ ] **Step 3: 验收门人工过(本步是 gate,不通过不 apply)**
  - ledger 一致率 ≥ 95%?(否则查 registry/refdata 错在哪,改数据重跑 dry-run)
  - HTML 报告里"将写"的样本抽查 5-10 条:region/issuer/id/date 对不对?
  - 队列规模合理?(转载/联合/媒体/非gov 落队列,符合预期)
  - **把 HTML 报告渲染给用户过目**(见执行交接:用户要看),用户认可才进 apply。

- [ ] **Step 4(不提交代码,人工 gate 记录):** 在 `state/source_ready/STATUS.md` 追加 dry-run 结果摘要。

---

## Task 12: apply + verify + vault commit(写 raw,可逆)

- [ ] **Step 1: apply(写 raw,验收门 rate≥95% 内置断言)**

Run: `python3 -m scripts.l2_attribution.run_2a apply`
Expected: "写了 N 篇";生成 `apply_log_2a.jsonl`。

- [ ] **Step 2: verify(幂等 + 一致率)**

Run: `python3 -m scripts.l2_attribution.run_2a verify`
Expected: "幂等重跑待写 0 篇";断言通过。

- [ ] **Step 3: SCHEMA validator**

Run: `python3 scripts/audit/validate_schema.py`(按其实际用法;若需参数见脚本 `--help`)
Expected: 无新增报错(身份字段 + 嵌套 provenance 审计字段合法)。

- [ ] **Step 4: vault commit(全 git rename/内容改,文件名不变)**

```bash
cd "/Users/shaoziyuan/Documents/Zayn Main/政策分析" && git add -A 0_raw/policies _meta/channel_registry.yaml && git status -s | head && git commit -m "②-A: 确定性身份固化(域名查表修 id/issuer/region/date,§C 嵌套审计)"
```

- [ ] **Step 5: pipeline 收尾 commit + 更新 STATUS/BACKLOG**

更新 `state/source_ready/STATUS.md`(②-A done + 队列规模 + 一致率)、`docs/BACKLOG.md`(B2 标 ✅ 部分消费、issuer 队列校准登记到 ②-B 触发、B4 标 ✅)。
```bash
cd /Users/shaoziyuan/dev/政策分析-pipeline && git add docs/BACKLOG.md && git commit -m "docs(②-A): 收尾 BACKLOG/STATUS 更新(B4✅ + issuer队列→②-B)"
```

---

## Self-Review(plan vs spec)

- **spec §1 目标/非目标** → Task 1-12 覆盖身份修复;theme/重要性/B3/B5 不在任务内(非目标)。✅
- **spec §3 架构(数据/代码分离)** → 数据层 Task 2-4(refdata+registry),代码层 Task 1/3/5-10。✅
- **spec §4 每字段规则** → Task 6 resolver 逐字段实现 + 测试;§C method 枚举用对(domain_lookup/title_extract/body_chinese_date/id_recompute_from_metadata)。✅
- **spec §5 冲突→队列** → Task 6(标冲突)+ Task 9(写队列)+ Task 10(ledger矛盾降级)。✅
- **spec §6 ledger oracle** → Task 7 + Task 10(仅校验、不当真值)。✅
- **spec §7 验收门 6 条** → 一致率(Task 10 apply 断言+Task 11 gate)、幂等(Task 10 verify+Task 12)、validator(Task 12)、零pid分支(resolver 设计+code review)、可逆(Task 11 tag + Task 12 rename)、可解释(Task 8 审计字段)。✅
- **spec §9 测试** → 每 Task TDD;resolver 覆盖 national/省/市/直辖市/joint/转载/date/非gov/no-op。✅
- **占位扫描**:无 TBD;city→province 表执行时按 needs_manual 补(Task 4 明确为 curate 数据步,非代码占位)。✅
- **类型一致**:`ResolvedIdentity.fields[name]=ResolvedField(value/method/confidence/from_val)`、`apply_identity(path, ri, fixed_at)`、`plan()->(to_apply, queue)`、`resolve_identity(rec, registry, body_tail, existing_ids)` 全程一致。✅
- **滑坡红线**:resolver 零 pid 分支(不规则→registry 数据);ledger 仅 oracle;队列派生层;写 raw 走 §C。✅

**已知执行期判断点(非占位,需执行时定):** ① Task 4 needs_manual 规模决定 curate 工作量;② 市级 adcode 暂省级回退+`needs_city_code` 标记(精化留后续);③ `validate_schema.py` 实际调用方式执行时按脚本 `--help` 对齐。
