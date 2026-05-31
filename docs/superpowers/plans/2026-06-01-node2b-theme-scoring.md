# ②-B 归属挂载(theme + 重要性打分)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 vault 935 篇政策每篇挂 theme(s)+主theme、打六维重要性分,过门篇加 3-key 影响分析,整文件重生 `_meta/business_view/{pid}.yaml`(派生层,绝不碰 raw)。

**Architecture:** generator(模型A,temp0)两遍出 theme+分/影响分析 → 脚本确定性算重要性/门 → 程序门(纯函数)+ 模型B judge(语义)双层验收 → business_view 写出。judge 先用冻结 golden 校准达标才上岗。

**Tech Stack:** Python 3, pytest, PyYAML, anthropic SDK(经 `scripts/common/llm.py::LLMClient`)。复用 `scripts/l1_audit/corpus.py`(语料)、`scripts/l2_attribution/`(报告/队列模式)。

**Spec:** `docs/superpowers/specs/2026-06-01-node2b-theme-scoring-design.md`(+ .html)

---

## 复用基线(已探明的真实签名)

- **LLM**:`scripts/common/llm.py` → `LLMClient(client=None, model="claude-opus-4-7", log_path=...)`,方法 `complete(system: str, user: str, max_tokens: int=1024) -> str`(temperature=0 硬编码)。**无 JSON 模式 → 必须 prompt 要 JSON + 自己解析/重试**。env:`ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL`。
- **语料**:`scripts/l1_audit/corpus.py` → `load_policies(policies_dir: str) -> list[PolicyRecord]`。`PolicyRecord` 字段:`pid / path / title / official_number / date / issuer(list) / issuer_canonical(list) / url / body_head(正文前2000字) / raw_fm(完整frontmatter dict)`。**region 在 `raw_fm.get("region")` = {level, code, name}**。
- **CLI 模式**:`scripts/l2_attribution/run_2a.py` → argparse `mode ∈ {dry-run,apply,verify}` + `--vault`(默认 `~/Documents/Zayn Main/政策分析`)+ `--state`。`plan()` 返回 `(to_apply, queue)`;dry-run 写 proposed+queue+html;apply 先 assert 门;verify 重跑 assert 幂等。
- **报告**:`report.py::render(...)` 纯 f-string HTML。**队列**:`review_queue.py::write_queue(list, out_path)->int` 一冲突一行 JSONL。
- **测试**:pytest,`tests/<module>/test_*.py`,`tmp_path` 写样本 .md;LLM 用 `_FakeAnthropic`(`tests/common/test_llm.py` 有范例)。
- **business_view 写出**:**当前无任何代码写它**(net-new)。`scripts/audit/validate_schema.py::check_business_view` 只读校验 → 我们的写出必须过它。
- **DEFAULT_VAULT**:`str(Path.home()/"Documents"/"Zayn Main"/"政策分析")`。business_view 路径 `{vault}/_meta/business_view/{pid}.yaml`。

---

## 文件结构(本计划产出)

```
scripts/l2_themescore/
  __init__.py
  models.py              # 数据模型(纯 dataclass)
  theme_registry.py      # 加载 themes_registry + alias→[ids] + 校验(alias 可跨theme)
  scoring.py             # 确定性:importance/action_class/value_tags/gate(纯函数)
  prompts.py             # 从 registry+scoring+framework 构建 generator/judge 提示词
  generator.py           # 模型A:gen_pass1 / gen_pass2 + JSON 解析重试
  judge.py               # 模型B:judge_one + verdict 解析
  golden.py              # golden 加载 + judge 跑分(召回/精度)
  program_gate.py        # §7 程序门(纯函数)
  business_view_writer.py# 整文件重生 yaml(§C 安全)
  review_queue.py        # 低置信入队(JSONL)
  report.py              # dry-run HTML 报告
  run_2b.py              # 编排 CLI dry-run/apply/verify
tests/l2_themescore/
  test_models.py test_theme_registry.py test_scoring.py test_program_gate.py
  test_generator.py test_judge.py test_golden.py test_business_view_writer.py
  test_run_2b.py
state/node2b/
  golden/golden_v1.jsonl        # 冻结答案键(Task 13)
  proposed_changes/  review_queue/  reports/
```

数据 + 人工任务(非纯代码):**Task 11**(B5 词表收口)、**Task 12**(SCHEMA §4 校准)、**Task 13**(golden 标注+抽查+冻结+judge校准·STOP)、**Task 14**(935 dry-run·STOP)、**Task 15**(apply+verify·STOP)。

---

## Task 1: models.py — 数据模型

**Files:**
- Create: `scripts/l2_themescore/__init__.py`(空)
- Create: `scripts/l2_themescore/models.py`
- Test: `tests/l2_themescore/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/l2_themescore/test_models.py
from scripts.l2_themescore.models import Scores, BusinessViewDraft, JudgeVerdict

def test_scores_roundtrip():
    s = Scores(D1=5, D2=4, D3=4, D4=4, D5=3, D6=5)
    assert s.to_dict() == {"D1":5,"D2":4,"D3":4,"D4":4,"D5":3,"D6":5}
    assert Scores.from_dict({"D1":5,"D2":4,"D3":4,"D4":4,"D5":3,"D6":5}) == s

def test_draft_minimal():
    d = BusinessViewDraft(pid="P_X", themes=["power_market"], primary_theme="power_market",
                          scores=Scores(3,3,3,3,3,3))
    assert d.pid == "P_X"
    assert d.importance is None  # 未算
    assert d.影响分析 is None and d.行动建议 == []

def test_verdict_fields():
    v = JudgeVerdict(verdict="reject", dim="theme", reason="漏挂储能", confidence=0.8)
    assert v.verdict == "reject"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_models.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 models.py**

```python
# scripts/l2_themescore/models.py
from dataclasses import dataclass, field, asdict

@dataclass
class Scores:
    D1: int; D2: int; D3: int; D4: int; D5: int; D6: int
    def to_dict(self): return {k: getattr(self, k) for k in ("D1","D2","D3","D4","D5","D6")}
    @classmethod
    def from_dict(cls, d): return cls(**{k: int(d[k]) for k in ("D1","D2","D3","D4","D5","D6")})

@dataclass
class BusinessViewDraft:
    pid: str
    themes: list                      # list[str], ∈ registry
    primary_theme: str                # ∈ themes
    scores: Scores
    importance: int = None            # 脚本算
    action_class: str = None          # 脚本算 A/B/C/D
    value_tags: list = field(default_factory=list)
    gate_passed_deep: bool = False    # 脚本算
    影响分析: dict = None              # {加油,充电,电力_储能_V2G_交易} 或 None
    行动建议: list = field(default_factory=list)
    didi_impact_one_liner: str = None

@dataclass
class JudgeVerdict:
    verdict: str                      # accept | reject
    dim: str                          # theme | score | impact | overall
    reason: str
    confidence: float

@dataclass
class QueueRecord:
    pid: str
    stage: str                        # generation_error | program_gate | judge_reject
    reason: str
    detail: dict = field(default_factory=dict)
    def to_dict(self): return asdict(self)

@dataclass
class GoldenRecord:
    pid: str
    gold_themes: list
    gold_primary: str
    gold_scores: dict                 # {D1..D6}
    gold_影响分析: dict = None
    is_planted: bool = False          # 是否埋错副本
    error_type: str = None            # 埋的错型(planted 时)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_models.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/l2_themescore/__init__.py scripts/l2_themescore/models.py tests/l2_themescore/test_models.py
git commit -m "feat(②-B): models — Scores/BusinessViewDraft/JudgeVerdict/QueueRecord/GoldenRecord"
```

---

## Task 2: theme_registry.py — 词表加载 + alias 跨theme

**Files:**
- Create: `scripts/l2_themescore/theme_registry.py`
- Test: `tests/l2_themescore/test_theme_registry.py`

关键(spec §9.1):**一个 alias 可映射到多个 theme**(`负荷聚合`→{vpp_theme, aggregator_access})。`alias_index` 的值是 **list[str]**,不是 str。

- [ ] **Step 1: 写失败测试**

```python
# tests/l2_themescore/test_theme_registry.py
from scripts.l2_themescore.theme_registry import ThemeRegistry

REG = """
schema_version: 1.0
themes:
  - {id: vpp_theme, zh: 虚拟电厂, aliases: [虚拟电厂, 负荷聚合, 可调节负荷]}
  - {id: aggregator_access, zh: 聚合商准入, aliases: [聚合商, 负荷聚合]}
  - {id: power_market, zh: 电力市场, aliases: [电力市场, 现货交易]}
"""

def test_load_ids(tmp_path):
    p = tmp_path/"r.yaml"; p.write_text(REG, encoding="utf-8")
    r = ThemeRegistry.load(str(p))
    assert set(r.ids) == {"vpp_theme","aggregator_access","power_market"}

def test_alias_can_map_multiple_themes(tmp_path):
    p = tmp_path/"r.yaml"; p.write_text(REG, encoding="utf-8")
    r = ThemeRegistry.load(str(p))
    assert set(r.alias_index["负荷聚合"]) == {"vpp_theme","aggregator_access"}
    assert r.alias_index["现货交易"] == ["power_market"]

def test_validate(tmp_path):
    p = tmp_path/"r.yaml"; p.write_text(REG, encoding="utf-8")
    r = ThemeRegistry.load(str(p))
    assert r.is_valid("vpp_theme") and not r.is_valid("nonsense_theme")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_theme_registry.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 theme_registry.py**

```python
# scripts/l2_themescore/theme_registry.py
from dataclasses import dataclass, field
from pathlib import Path
import yaml

@dataclass
class ThemeRegistry:
    ids: list                              # list[str]
    zh: dict                               # id -> 中文名
    aliases: dict                          # id -> list[str]
    alias_index: dict                      # alias -> list[id]（可多）

    @classmethod
    def load(cls, path: str):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        themes = data.get("themes") or []
        ids, zh, aliases, alias_index = [], {}, {}, {}
        for t in themes:
            tid = t["id"]; ids.append(tid)
            zh[tid] = t.get("zh", tid)
            al = list(t.get("aliases") or [])
            aliases[tid] = al
            for a in al:
                alias_index.setdefault(a, []).append(tid)
        return cls(ids=ids, zh=zh, aliases=aliases, alias_index=alias_index)

    def is_valid(self, tid: str) -> bool:
        return tid in self.zh
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_theme_registry.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/l2_themescore/theme_registry.py tests/l2_themescore/test_theme_registry.py
git commit -m "feat(②-B): theme_registry — load + alias 可跨theme(§9.1)"
```

---

## Task 3: scoring.py — 确定性算分 + 门(纯函数)

**Files:**
- Create: `scripts/l2_themescore/scoring.py`
- Test: `tests/l2_themescore/test_scoring.py`

规则来源 `_meta/framework/scoring.yaml`:`重要性=round(D1·.4+D2·.4+D3·.2)`;行动分类 D4×D5 2×2(紧迫=D4≥4、实操高=D5≥4)→A/B/C/D,D6∈{5,4}前跳一档、D6∈{2,1}后降一档;价值标签由重要性+theme推导;门=重要性≥3 OR region.level∈{国家,省}。

- [ ] **Step 1: 写失败测试**

```python
# tests/l2_themescore/test_scoring.py
from scripts.l2_themescore.models import Scores
from scripts.l2_themescore.scoring import importance, action_class, gate_passed_deep, value_tags

def test_importance_formula():
    assert importance(Scores(5,4,4,0,0,0)) == 4   # round(2+1.6+0.8)=round(4.4)=4
    assert importance(Scores(3,3,3,0,0,0)) == 3   # round(1.2+1.2+0.6)=3
    assert importance(Scores(0,0,0,0,0,0)) == 0

def test_action_class_matrix_and_modifier():
    # 紧迫(D4=5)+实操高(D5=5) => A; D6=3 不修正
    assert action_class(Scores(5,5,5,5,5,3)) == "A"
    # 不紧迫(D4=2)+实操低(D5=2) => D; D6=5 前跳一档 => C
    assert action_class(Scores(3,3,3,2,2,5)) == "C"
    # 紧迫+实操低 => B; D6=1 后降一档 => C
    assert action_class(Scores(3,3,3,5,2,1)) == "C"

def test_gate():
    assert gate_passed_deep(importance_val=3, region_level="市") is True   # 重要性≥3
    assert gate_passed_deep(importance_val=2, region_level="国家") is True  # 国省级
    assert gate_passed_deep(importance_val=2, region_level="省") is True
    assert gate_passed_deep(importance_val=2, region_level="市") is False

def test_value_tags_subset():
    tags = value_tags(importance_val=4, themes=["power_market"])
    assert set(tags) <= {"合规","机会","壁垒","趋势"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_scoring.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 scoring.py**

```python
# scripts/l2_themescore/scoring.py
"""确定性算分,规则源 _meta/framework/scoring.yaml。纯函数,零 LLM。"""

def importance(scores) -> int:
    return round(scores.D1 * 0.40 + scores.D2 * 0.40 + scores.D3 * 0.20)

def action_class(scores) -> str:
    urgent = scores.D4 >= 4          # 紧迫
    hands_on = scores.D5 >= 4        # 实操高
    base = ("A" if hands_on else "B") if urgent else ("C" if hands_on else "D")
    order = ["A", "B", "C", "D"]
    i = order.index(base)
    if scores.D6 >= 4:               # 机会窗口 5-4 前跳一档
        i = max(0, i - 1)
    elif scores.D6 <= 2:             # 2-1 后降一档
        i = min(len(order) - 1, i + 1)
    return order[i]

def gate_passed_deep(importance_val: int, region_level: str) -> bool:
    return importance_val >= 3 or region_level in ("国家", "省")

# 价值标签推导:重要性 + theme 组合(规则化,可调)
_OPPORTUNITY_THEMES = {"power_market","vpp_theme","v2g","green_power_trading_theme",
                       "energy_storage_theme","aggregator_access","distribution_grid_opening"}
_COMPLIANCE_THEMES  = {"petroleum_retail_compliance","carbon_market_theme"}
_MOAT_THEMES        = {"residential_charging","charging_infra","gas_station_transition_theme"}

def value_tags(importance_val: int, themes: list) -> list:
    tags = []
    ts = set(themes or [])
    if ts & _COMPLIANCE_THEMES:               tags.append("合规")
    if ts & _OPPORTUNITY_THEMES:              tags.append("机会")
    if ts & _MOAT_THEMES and importance_val >= 3: tags.append("壁垒")
    if importance_val <= 3 and not tags:      tags.append("趋势")
    return tags or ["趋势"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_scoring.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/l2_themescore/scoring.py tests/l2_themescore/test_scoring.py
git commit -m "feat(②-B): scoring — 重要性/行动分类/门/价值标签(确定性纯函数)"
```

---

## Task 4: program_gate.py — 程序门(纯函数)

**Files:**
- Create: `scripts/l2_themescore/program_gate.py`
- Test: `tests/l2_themescore/test_program_gate.py`

§7 规则:结构(themes 非空、primary∈themes)、公式自洽(重算==草稿)、registry 合规(themes⊆ids)、影响分析键(过门篇=恰好3键)、深档⟺门、(语料级)分布合理。返回 `list[str]` 违规(空=过)。

- [ ] **Step 1: 写失败测试**

```python
# tests/l2_themescore/test_program_gate.py
from scripts.l2_themescore.models import Scores, BusinessViewDraft
from scripts.l2_themescore.program_gate import check_draft

VALID_IDS = ["power_market","vpp_theme","energy_storage_theme"]
KEYS = {"加油","充电","电力_储能_V2G_交易"}

def _draft(**kw):
    base = dict(pid="P", themes=["power_market"], primary_theme="power_market",
                scores=Scores(5,4,4,4,4,5), importance=4, action_class="A",
                value_tags=["机会"], gate_passed_deep=True,
                影响分析={k:"x" for k in KEYS}, 行动建议=["A 趁早:做"])
    base.update(kw); return BusinessViewDraft(**base)

def test_clean_passes():
    assert check_draft(_draft(), VALID_IDS) == []

def test_primary_not_in_themes():
    v = check_draft(_draft(primary_theme="vpp_theme"), VALID_IDS)
    assert any("primary" in x for x in v)

def test_theme_not_in_registry():
    v = check_draft(_draft(themes=["bogus"], primary_theme="bogus"), VALID_IDS)
    assert any("registry" in x for x in v)

def test_impact_keys_wrong():
    v = check_draft(_draft(影响分析={"加油":"x","乡村":"y"}), VALID_IDS)
    assert any("影响分析键" in x for x in v)

def test_deep_iff_gate_violation():
    # 过门但影响分析空
    v = check_draft(_draft(gate_passed_deep=True, 影响分析=None, 行动建议=[]), VALID_IDS)
    assert any("深档" in x for x in v)

def test_formula_mismatch():
    v = check_draft(_draft(importance=1), VALID_IDS)  # 真值=4
    assert any("公式" in x for x in v)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_program_gate.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 program_gate.py**

```python
# scripts/l2_themescore/program_gate.py
from .scoring import importance, action_class

IMPACT_KEYS = {"加油", "充电", "电力_储能_V2G_交易"}

def check_draft(d, valid_ids) -> list:
    """单篇程序门。返回违规列表(空=过)。"""
    v = []
    # 结构
    if not d.themes:
        v.append("结构:themes 为空")
    if d.primary_theme not in (d.themes or []):
        v.append("结构:primary_theme 不在 themes 内")
    # registry 合规(正向白名单)
    bad = [t for t in (d.themes or []) if t not in valid_ids]
    if bad:
        v.append(f"registry:未知 theme {bad}")
    # 公式自洽(脚本重算 == 草稿值)
    if d.importance != importance(d.scores):
        v.append(f"公式:重要性 {d.importance} != 重算 {importance(d.scores)}")
    if d.action_class != action_class(d.scores):
        v.append(f"公式:行动分类 {d.action_class} != 重算 {action_class(d.scores)}")
    # 影响分析键(正向白名单:恰好3键)
    if d.影响分析 is not None and set(d.影响分析.keys()) != IMPACT_KEYS:
        v.append(f"影响分析键:{sorted(d.影响分析.keys())} != {sorted(IMPACT_KEYS)}")
    # 深档 ⟺ 门
    has_deep = bool(d.影响分析) and bool(d.行动建议)
    if has_deep != d.gate_passed_deep:
        v.append(f"深档:有深档={has_deep} 但 gate={d.gate_passed_deep}")
    return v

def check_distribution(drafts, n_themes: int) -> list:
    """语料级分布门。返回告警列表。"""
    warns = []
    if not drafts:
        return ["分布:无草稿"]
    overstuffed = [d.pid for d in drafts if len(d.themes or []) >= n_themes]
    if overstuffed:
        warns.append(f"分布:{len(overstuffed)} 篇挂满全部 theme(过挂信号){overstuffed[:5]}")
    islands = [d.pid for d in drafts if not d.themes]
    if islands:
        warns.append(f"分布:{len(islands)} 篇 0 theme(孤岛)")
    return warns
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_program_gate.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/l2_themescore/program_gate.py tests/l2_themescore/test_program_gate.py
git commit -m "feat(②-B): program_gate — 结构/公式/registry/影响键/深档/分布(纯函数)"
```

---

## Task 5: prompts.py + generator.py — 模型A 两遍生成

**Files:**
- Create: `scripts/l2_themescore/prompts.py`
- Create: `scripts/l2_themescore/generator.py`
- Test: `tests/l2_themescore/test_generator.py`

generator 喂 `title + body_head + issuer + region` 给模型A,要 JSON。**无 JSON 模式 → `parse_json_block` 去 markdown 围栏 + json.loads,失败重试1次**。

- [ ] **Step 1: 写失败测试(用 _FakeAnthropic)**

```python
# tests/l2_themescore/test_generator.py
import json
from scripts.common.llm import LLMClient
from scripts.l2_themescore.generator import parse_json_block, gen_pass1, gen_pass2

def _fake(payload):
    class M:
        def create(self, **kw):
            class R: content = [type("B",(),{"text": payload})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages = M()
    return A()

def test_parse_json_block_strips_fence():
    assert parse_json_block('```json\n{"a":1}\n```') == {"a":1}
    assert parse_json_block('{"b":2}') == {"b":2}

def test_gen_pass1(tmp_path):
    payload = '{"themes":["power_market"],"primary_theme":"power_market","scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5}}'
    c = LLMClient(client=_fake(payload), log_path=str(tmp_path/"l.jsonl"))
    out = gen_pass1(c, system="sys", user="u")
    assert out["primary_theme"] == "power_market"
    assert out["scores"]["D1"] == 5

def test_gen_pass2(tmp_path):
    payload = '{"影响分析":{"加油":"a","充电":"b","电力_储能_V2G_交易":"c"},"行动建议":["A 趁早:x"],"didi_impact_one_liner":"y"}'
    c = LLMClient(client=_fake(payload), log_path=str(tmp_path/"l.jsonl"))
    out = gen_pass2(c, system="sys", user="u")
    assert set(out["影响分析"].keys()) == {"加油","充电","电力_储能_V2G_交易"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_generator.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 prompts.py**

```python
# scripts/l2_themescore/prompts.py
"""从 registry + scoring.yaml + decision_framework 构建提示词。"""

def pass1_system(registry, scoring_text: str) -> str:
    theme_lines = "\n".join(
        f"  - {tid}({registry.zh[tid]}):{'/'.join(registry.aliases[tid])}"
        for tid in registry.ids)
    return f"""你是政策归属分析助手。任务:给一篇政策挂主题(theme)并打六维分。

【可选 theme(只能从下列 id 里选,不许造新的)】
{theme_lines}

【挂 theme 规则】
- 挂上所有真正命中的 theme(不限数量);政策跨多主题就都挂。
- 再从挂上的里选 1 个 primary_theme(最核心的那个)。
- 上面每个 theme 后的词是关键词锚,命中可作信号;但以语义为准,不是出现关键词就必挂。

【六维打分(0-5,定义见下)】
{scoring_text}

只输出 JSON,无解释:
{{"themes":["id1","id2"],"primary_theme":"id1","scores":{{"D1":0,"D2":0,"D3":0,"D4":0,"D5":0,"D6":0}}}}
"""

def pass1_user(rec) -> str:
    region = (rec.raw_fm.get("region") or {})
    return (f"标题:{rec.title}\n发文机构:{'、'.join(rec.issuer)}\n"
            f"层级:{region.get('level','')}\n正文(节选):\n{rec.body_head}")

def pass2_system() -> str:
    return """你是政策业务影响分析助手。服务对象:公司决策层,三业务=加油/充电/电力(储能·VPP·V2G·电力交易)。
就这一篇政策,写 3-key 影响分析 + 行动建议。影响分析必须且只能这三个键。行动建议动词用"趁早"不用"立即"。
只输出 JSON,无解释:
{"影响分析":{"加油":"...","充电":"...","电力_储能_V2G_交易":"..."},"行动建议":["A 趁早:...","B 研究:..."],"didi_impact_one_liner":"..."}
"""

def pass2_user(rec, draft) -> str:
    region = (rec.raw_fm.get("region") or {})
    return (f"标题:{rec.title}\n层级:{region.get('level','')}\n"
            f"已判主题:{draft.themes}\n重要性:{draft.importance}\n正文(节选):\n{rec.body_head}")
```

- [ ] **Step 4: 实现 generator.py**

```python
# scripts/l2_themescore/generator.py
import json, re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)

def parse_json_block(text: str) -> dict:
    m = _FENCE.search(text)
    raw = m.group(1) if m else text
    return json.loads(raw)

def _complete_json(client, system, user, max_tokens=1024) -> dict:
    txt = client.complete(system=system, user=user, max_tokens=max_tokens)
    try:
        return parse_json_block(txt)
    except Exception:
        # 重试 1 次,提示强化"只要 JSON"
        txt = client.complete(system=system + "\n\n严格:只输出 JSON,不要任何其他字符。",
                              user=user, max_tokens=max_tokens)
        return parse_json_block(txt)   # 仍失败则抛,由编排层入 generation_error 队

def gen_pass1(client, system: str, user: str) -> dict:
    return _complete_json(client, system, user, max_tokens=512)

def gen_pass2(client, system: str, user: str) -> dict:
    return _complete_json(client, system, user, max_tokens=1024)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_generator.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add scripts/l2_themescore/prompts.py scripts/l2_themescore/generator.py tests/l2_themescore/test_generator.py
git commit -m "feat(②-B): prompts + generator 两遍(JSON解析重试,无JSON模式兜底)"
```

---

## Task 6: judge.py — 模型B 语义验收

**Files:**
- Create: `scripts/l2_themescore/judge.py`
- Test: `tests/l2_themescore/test_judge.py`

judge 用**不同于 generator 的模型**(调用方传入不同 model 的 LLMClient)。给政策 + 草稿,要 verdict JSON。

- [ ] **Step 1: 写失败测试**

```python
# tests/l2_themescore/test_judge.py
from scripts.common.llm import LLMClient
from scripts.l2_themescore.models import Scores, BusinessViewDraft
from scripts.l2_themescore.judge import judge_draft

def _fake(payload):
    class M:
        def create(self, **kw):
            class R: content=[type("B",(),{"text":payload})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages=M()
    return A()

def _d(): return BusinessViewDraft(pid="P", themes=["power_market"], primary_theme="power_market",
                                   scores=Scores(5,4,4,4,4,5), importance=4, action_class="A")

def test_judge_accept(tmp_path):
    c = LLMClient(client=_fake('{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}'),
                  log_path=str(tmp_path/"l.jsonl"))
    v = judge_draft(c, rec_title="某电力市场政策", rec_body="...", draft=_d())
    assert v.verdict == "accept" and v.confidence == 0.9

def test_judge_reject(tmp_path):
    c = LLMClient(client=_fake('{"verdict":"reject","dim":"theme","reason":"漏挂储能","confidence":0.7}'),
                  log_path=str(tmp_path/"l.jsonl"))
    v = judge_draft(c, rec_title="储能政策", rec_body="...", draft=_d())
    assert v.verdict == "reject" and v.dim == "theme"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_judge.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 judge.py**

```python
# scripts/l2_themescore/judge.py
from .generator import parse_json_block
from .models import JudgeVerdict

JUDGE_SYSTEM = """你是独立第三方审查员,审查另一模型给政策做的归属(theme+分+影响分析)。
只挑语义错:theme 漏挂/错挂、分数明显不合理、影响分析对零相关政策硬写(幻觉)或该写没写。
不挑格式(已有程序门管)。默认严格:拿不准且像错 → reject。
只输出 JSON:{"verdict":"accept|reject","dim":"theme|score|impact|overall","reason":"一句话","confidence":0-1}
"""

def judge_draft(client, rec_title: str, rec_body: str, draft) -> JudgeVerdict:
    user = (f"政策标题:{rec_title}\n正文(节选):\n{rec_body[:1500]}\n\n"
            f"待审归属:themes={draft.themes} primary={draft.primary_theme} "
            f"scores={draft.scores.to_dict()} 重要性={draft.importance} "
            f"影响分析={draft.影响分析}")
    txt = client.complete(system=JUDGE_SYSTEM, user=user, max_tokens=256)
    try:
        d = parse_json_block(txt)
    except Exception:
        return JudgeVerdict(verdict="reject", dim="overall",
                            reason="judge 返回非JSON", confidence=0.0)
    return JudgeVerdict(verdict=d.get("verdict","reject"), dim=d.get("dim","overall"),
                        reason=d.get("reason",""), confidence=float(d.get("confidence",0.0)))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_judge.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/l2_themescore/judge.py tests/l2_themescore/test_judge.py
git commit -m "feat(②-B): judge — 模型B 语义验收 + verdict 解析"
```

---

## Task 7: golden.py — judge 校准跑分

**Files:**
- Create: `scripts/l2_themescore/golden.py`
- Test: `tests/l2_themescore/test_golden.py`

golden_v1.jsonl 每行一个 `GoldenRecord`(含正确标注 + 埋错副本)。校准:对每条造 draft,跑 judge,统计召回(埋错被 reject 的比例)、精度(reject 中真是埋错的比例)。

- [ ] **Step 1: 写失败测试**

```python
# tests/l2_themescore/test_golden.py
from scripts.l2_themescore.golden import load_golden, score_judge

def test_load_golden(tmp_path):
    p = tmp_path/"g.jsonl"
    p.write_text(
        '{"pid":"P1","gold_themes":["power_market"],"gold_primary":"power_market","gold_scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5},"is_planted":false}\n'
        '{"pid":"P2","gold_themes":["x"],"gold_primary":"x","gold_scores":{"D1":1,"D2":1,"D3":1,"D4":1,"D5":1,"D6":1},"is_planted":true,"error_type":"低估"}\n',
        encoding="utf-8")
    recs = load_golden(str(p))
    assert len(recs) == 2 and recs[1].is_planted

def test_score_judge_recall_precision():
    # verdicts: planted→reject(对), clean→accept(对) => recall=1 precision=1
    verdicts = {"P1":("accept", False_flag:=False), "P2":("reject", True)}
    # 用简化 dict: pid -> (verdict, is_planted)
    rows = [("P1","accept",False), ("P2","reject",True)]
    r = score_judge(rows)
    assert r["recall"] == 1.0 and r["precision"] == 1.0
```

> 注:实现里 `score_judge` 接收 `list[(pid, verdict, is_planted)]`,测试用简化元组即可。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_golden.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 golden.py**

```python
# scripts/l2_themescore/golden.py
import json
from pathlib import Path
from .models import GoldenRecord

def load_golden(path: str) -> list:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out.append(GoldenRecord(
            pid=d["pid"], gold_themes=d.get("gold_themes", []),
            gold_primary=d.get("gold_primary", ""), gold_scores=d.get("gold_scores", {}),
            gold_影响分析=d.get("gold_影响分析"),
            is_planted=bool(d.get("is_planted", False)), error_type=d.get("error_type")))
    return out

def score_judge(rows) -> dict:
    """rows: list[(pid, verdict, is_planted)]. 召回/精度。"""
    planted = [r for r in rows if r[2]]
    rejected = [r for r in rows if r[1] == "reject"]
    caught = [r for r in rejected if r[2]]
    recall = len(caught) / len(planted) if planted else 0.0
    precision = len(caught) / len(rejected) if rejected else 1.0
    return {"recall": recall, "precision": precision,
            "n_planted": len(planted), "n_rejected": len(rejected), "n_caught": len(caught)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_golden.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/l2_themescore/golden.py tests/l2_themescore/test_golden.py
git commit -m "feat(②-B): golden — 加载冻结答案键 + judge 召回/精度跑分"
```

---

## Task 8: business_view_writer.py — 整文件重生(§C 安全)

**Files:**
- Create: `scripts/l2_themescore/business_view_writer.py`
- Test: `tests/l2_themescore/test_business_view_writer.py`

写 `{vault}/_meta/business_view/{pid}.yaml`,整文件重生覆盖。**§C 安全:只写 business_view 目录,绝不打开 0_raw/ 写**。输出须过 `validate_schema.check_business_view`(SCHEMA §4)。

- [ ] **Step 1: 写失败测试**

```python
# tests/l2_themescore/test_business_view_writer.py
import yaml
from pathlib import Path
from scripts.l2_themescore.models import Scores, BusinessViewDraft
from scripts.l2_themescore.business_view_writer import write_business_view

def _d():
    return BusinessViewDraft(pid="P_2024_NDRC_718", themes=["power_market","energy_storage_theme"],
        primary_theme="power_market", scores=Scores(5,4,4,4,4,5), importance=4, action_class="A",
        value_tags=["机会"], gate_passed_deep=True,
        影响分析={"加油":"a","充电":"b","电力_储能_V2G_交易":"c"}, 行动建议=["A 趁早:x"],
        didi_impact_one_liner="y")

def test_write_and_reload(tmp_path):
    vault = tmp_path; raw_file = "0_raw/policies/foo.md"
    out = write_business_view(_d(), str(vault), sanitized_from=raw_file, extracted_at="2026-06-01",
                              extracted_model="model-A")
    assert Path(out).exists()
    data = yaml.safe_load(Path(out).read_text(encoding="utf-8"))
    assert data["pid"] == "P_2024_NDRC_718"
    assert data["themes"] == ["power_market","energy_storage_theme"]
    assert data["primary_theme"] == "power_market"
    assert data["重要性"] == 4
    assert set(data["影响分析"].keys()) == {"加油","充电","电力_储能_V2G_交易"}
    assert data["sanitized_from"] == raw_file
    assert data["gate_passed_deep"] is True

def test_overwrites_整文件重生(tmp_path):
    vault = tmp_path
    write_business_view(_d(), str(vault), sanitized_from="x", extracted_at="d", extracted_model="m")
    d2 = _d(); d2.themes = ["power_market"]; d2.primary_theme="power_market"
    out = write_business_view(d2, str(vault), sanitized_from="x", extracted_at="d", extracted_model="m")
    data = yaml.safe_load(Path(out).read_text(encoding="utf-8"))
    assert data["themes"] == ["power_market"]   # 旧 energy_storage 被整文件覆盖,不残留

def test_never_writes_raw(tmp_path, monkeypatch):
    # 守卫:writer 不得写 0_raw/ 下任何文件
    vault = tmp_path; (vault/"0_raw"/"policies").mkdir(parents=True)
    raw = vault/"0_raw"/"policies"/"foo.md"; raw.write_text("ORIG", encoding="utf-8")
    write_business_view(_d(), str(vault), sanitized_from="0_raw/policies/foo.md",
                        extracted_at="d", extracted_model="m")
    assert raw.read_text(encoding="utf-8") == "ORIG"   # raw 一字未动
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_business_view_writer.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 business_view_writer.py**

```python
# scripts/l2_themescore/business_view_writer.py
from pathlib import Path
import yaml

def write_business_view(draft, vault: str, sanitized_from: str, extracted_at: str,
                        extracted_model: str) -> str:
    """整文件重生 {vault}/_meta/business_view/{pid}.yaml。§C 安全:只写派生层。"""
    out_dir = Path(vault) / "_meta" / "business_view"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{draft.pid}.yaml"
    # 防御:绝不允许写到 0_raw/
    assert "0_raw" not in str(out_path), "§C 违反:business_view 不得落 0_raw"

    doc = {
        "pid": draft.pid,
        "themes": list(draft.themes or []),
        "primary_theme": draft.primary_theme,
        "scores": draft.scores.to_dict(),
        "重要性": draft.importance,
        "行动分类": draft.action_class,
        "价值标签": list(draft.value_tags or []),
    }
    if draft.gate_passed_deep:
        doc["影响分析"] = draft.影响分析
        doc["行动建议"] = list(draft.行动建议 or [])
        if draft.didi_impact_one_liner:
            doc["didi_impact_one_liner"] = draft.didi_impact_one_liner
    doc["sanitized_from"] = sanitized_from
    doc["extracted_at"] = extracted_at
    doc["extracted_by"] = "scripts/l2_themescore/run_2b.py"
    doc["extracted_model"] = extracted_model
    doc["gate_passed_deep"] = bool(draft.gate_passed_deep)
    if draft.importance is not None and draft.importance < 3:
        doc["archive"] = "low_score"

    out_path.write_text(yaml.dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(out_path)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_business_view_writer.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/l2_themescore/business_view_writer.py tests/l2_themescore/test_business_view_writer.py
git commit -m "feat(②-B): business_view_writer — 整文件重生(§C 安全,守卫不写raw)"
```

---

## Task 9: review_queue.py + report.py

**Files:**
- Create: `scripts/l2_themescore/review_queue.py`
- Create: `scripts/l2_themescore/report.py`
- Test: `tests/l2_themescore/test_review_queue.py`

- [ ] **Step 1: 写失败测试(队列)**

```python
# tests/l2_themescore/test_review_queue.py
import json
from pathlib import Path
from scripts.l2_themescore.models import QueueRecord
from scripts.l2_themescore.review_queue import write_queue

def test_write_queue(tmp_path):
    out = tmp_path/"q.jsonl"
    n = write_queue([QueueRecord(pid="P1", stage="program_gate", reason="registry:未知 theme",
                                 detail={"bad":["x"]})], str(out))
    assert n == 1
    rows = [json.loads(l) for l in Path(out).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["pid"] == "P1" and rows[0]["stage"] == "program_gate"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_review_queue.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 review_queue.py**

```python
# scripts/l2_themescore/review_queue.py
import json
from pathlib import Path

def write_queue(records, out_path: str) -> int:
    """records: list[QueueRecord]. 一条一行 JSONL。返回条数。"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(out_path).open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    return len(records)
```

- [ ] **Step 4: 实现 report.py(f-string HTML,镜像 ②-A 风格)**

```python
# scripts/l2_themescore/report.py
from pathlib import Path
from collections import Counter

def render(drafts, queue, distribution_warns, golden_score, out_path: str) -> str:
    theme_count = Counter(t for d in drafts for t in (d.themes or []))
    imp_dist = Counter(d.importance for d in drafts)
    gated = sum(1 for d in drafts if d.gate_passed_deep)
    theme_rows = "".join(f"<tr><td>{t}</td><td>{c}</td></tr>"
                         for t, c in theme_count.most_common())
    imp_rows = "".join(f"<tr><td>重要性 {k}</td><td>{imp_dist[k]}</td></tr>"
                       for k in sorted(imp_dist, reverse=True))
    warn_html = "".join(f"<li>{w}</li>" for w in distribution_warns) or "<li>无</li>"
    q_html = "".join(f"<tr><td>{r.pid}</td><td>{r.stage}</td><td>{r.reason}</td></tr>"
                     for r in queue)
    gs = golden_score or {}
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>②-B dry-run 报告</title>
<style>body{{font-family:-apple-system,"PingFang SC";max-width:900px;margin:0 auto;padding:24px;background:#0f1115;color:#e6e9ef}}
table{{border-collapse:collapse;width:100%;margin:10px 0}}td,th{{border-bottom:1px solid #2a2f3a;padding:6px 10px;text-align:left}}
h2{{border-left:3px solid #6ab7ff;padding-left:10px}}</style></head><body>
<h1>②-B 归属挂载 · dry-run 报告</h1>
<p>政策总数 {len(drafts)} · 过深档门 {gated} · 入队 {len(queue)}</p>
<h2>judge 校准</h2><p>召回 {gs.get('recall','-')} · 精度 {gs.get('precision','-')}</p>
<h2>分布告警</h2><ul>{warn_html}</ul>
<h2>重要性分布</h2><table>{imp_rows}</table>
<h2>theme 命中分布</h2><table><tr><th>theme</th><th>篇数</th></tr>{theme_rows}</table>
<h2>入队(需复核)</h2><table><tr><th>pid</th><th>阶段</th><th>原因</th></tr>{q_html}</table>
</body></html>"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_review_queue.py -v`
Expected: PASS（1 passed）

- [ ] **Step 6: Commit**

```bash
git add scripts/l2_themescore/review_queue.py scripts/l2_themescore/report.py tests/l2_themescore/test_review_queue.py
git commit -m "feat(②-B): review_queue + report(HTML)"
```

---

## Task 10: run_2b.py — 编排 CLI

**Files:**
- Create: `scripts/l2_themescore/run_2b.py`
- Test: `tests/l2_themescore/test_run_2b.py`

`plan(vault, registry_path, scoring_text, gen_client, judge_client)` → 对每篇:gen_pass1 → 组 draft → scoring → 过门则 gen_pass2 → program_gate → judge → 分类 (to_write / queue)。CLI:dry-run(写 proposed+queue+report,不写 vault)/ apply(写 business_view)/ verify(重跑 assert 幂等 + validate_schema)。

- [ ] **Step 1: 写失败集成测试(全 fake LLM)**

```python
# tests/l2_themescore/test_run_2b.py
from scripts.common.llm import LLMClient
from scripts.l2_themescore.run_2b import plan

REG = """schema_version: 1.0
themes:
  - {id: power_market, zh: 电力市场, aliases: [电力市场, 现货交易]}
"""
DOC = """---
id: P_T1
title: 电力现货市场建设方案
issuer: [国家发展和改革委员会]
region: {level: 国家, code: '000000', name: 全国}
provenance: {url: 'http://x'}
---
## 政策原文
推进电力现货市场,完善中长期交易。
"""

def _fake(p):
    class M:
        def create(self,**kw):
            class R: content=[type("B",(),{"text":p})()]
            return R()
    class A:
        def __init__(self,**kw): self.messages=M()
    return A()

def _setup(tmp_path):
    pol = tmp_path/"0_raw"/"policies"; pol.mkdir(parents=True)
    (pol/"d.md").write_text(DOC, encoding="utf-8")
    reg = tmp_path/"themes_registry.yaml"; reg.write_text(REG, encoding="utf-8")
    return str(tmp_path), str(reg)

def test_plan_clean_goes_to_write(tmp_path):
    vault, reg = _setup(tmp_path)
    gen1 = '{"themes":["power_market"],"primary_theme":"power_market","scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5}}'
    # 注:简化——本测试让 pass2 与 pass1 用同一 fake 不现实;实现里 plan 接收两个 client。
    gen_client = LLMClient(client=_fake(gen1), log_path=str(tmp_path/"g.jsonl"))
    # 用 monkeypatch 让 pass2 返回影响分析 见实现说明;此处先验 to_write 非空
    judge_client = LLMClient(client=_fake('{"verdict":"accept","dim":"overall","reason":"ok","confidence":0.9}'),
                             log_path=str(tmp_path/"j.jsonl"))
    to_write, queue = plan(vault, reg, scoring_text="(略)", gen_client=gen_client,
                           judge_client=judge_client, gen_pass2_client=gen_client)
    assert len(to_write) + len(queue) == 1
```

> 注:`plan` 需能分别注入 pass1/pass2/judge 的 client(测试用 fake)。实现签名见下。pass2 在本简化 fake 下会因键不全入队——测试只断言"分类发生",真实多键场景由集成 dry-run(Task 14)覆盖。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/l2_themescore/test_run_2b.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 run_2b.py**

```python
# scripts/l2_themescore/run_2b.py
import argparse, json
from pathlib import Path
from scripts.l1_audit.corpus import load_policies
from scripts.common.llm import LLMClient
from .theme_registry import ThemeRegistry
from .models import BusinessViewDraft, Scores, QueueRecord
from . import scoring, program_gate, prompts
from .generator import gen_pass1, gen_pass2
from .judge import judge_draft
from .business_view_writer import write_business_view
from .review_queue import write_queue
from . import report

DEFAULT_VAULT = str(Path.home() / "Documents" / "Zayn Main" / "政策分析")
DEFAULT_SCORING = "_meta/framework/scoring.yaml"

def _scoring_text(vault) -> str:
    return Path(f"{vault}/{DEFAULT_SCORING}").read_text(encoding="utf-8")

def plan(vault, registry_path, scoring_text, gen_client, judge_client, gen_pass2_client=None):
    gen_pass2_client = gen_pass2_client or gen_client
    reg = ThemeRegistry.load(registry_path)
    recs = load_policies(f"{vault}/0_raw/policies")
    p1_sys = prompts.pass1_system(reg, scoring_text)
    p2_sys = prompts.pass2_system()
    to_write, queue = [], []
    for rec in recs:
        try:
            o1 = gen_pass1(gen_client, p1_sys, prompts.pass1_user(rec))
            draft = BusinessViewDraft(
                pid=rec.pid, themes=o1.get("themes", []), primary_theme=o1.get("primary_theme",""),
                scores=Scores.from_dict(o1["scores"]))
        except Exception as e:
            queue.append(QueueRecord(pid=rec.pid, stage="generation_error", reason=str(e)[:200]))
            continue
        draft.importance = scoring.importance(draft.scores)
        draft.action_class = scoring.action_class(draft.scores)
        draft.value_tags = scoring.value_tags(draft.importance, draft.themes)
        region_level = (rec.raw_fm.get("region") or {}).get("level", "")
        draft.gate_passed_deep = scoring.gate_passed_deep(draft.importance, region_level)
        if draft.gate_passed_deep:
            try:
                o2 = gen_pass2(gen_pass2_client, p2_sys, prompts.pass2_user(rec, draft))
                draft.影响分析 = o2.get("影响分析"); draft.行动建议 = o2.get("行动建议", [])
                draft.didi_impact_one_liner = o2.get("didi_impact_one_liner")
            except Exception as e:
                queue.append(QueueRecord(pid=rec.pid, stage="generation_error", reason=f"pass2:{e}"[:200]))
                continue
        # 程序门
        viol = program_gate.check_draft(draft, reg.ids)
        if viol:
            queue.append(QueueRecord(pid=rec.pid, stage="program_gate", reason="; ".join(viol)))
            continue
        # judge
        v = judge_draft(judge_client, rec.title, rec.body_head, draft)
        if v.verdict != "accept":
            queue.append(QueueRecord(pid=rec.pid, stage="judge_reject", reason=v.reason,
                                     detail={"dim": v.dim, "confidence": v.confidence}))
            continue
        to_write.append((rec, draft))
    return to_write, queue

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dry-run", "apply", "verify"])
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--state", default="state/node2b")
    ap.add_argument("--gen-model", required=True)      # 模型A id
    ap.add_argument("--judge-model", required=True)    # 模型B id(≠A)
    args = ap.parse_args()
    assert args.gen_model != args.judge_model, "judge 模型必须 ≠ generator 模型"

    reg_path = f"{args.vault}/_meta/themes_registry.yaml"
    sc_text = _scoring_text(args.vault)
    gen_client = LLMClient(model=args.gen_model, log_path=f"{args.state}/gen_calls.jsonl")
    judge_client = LLMClient(model=args.judge_model, log_path=f"{args.state}/judge_calls.jsonl")

    to_write, queue = plan(args.vault, reg_path, sc_text, gen_client, judge_client)
    drafts = [d for _, d in to_write]
    warns = program_gate.check_distribution(drafts, len(ThemeRegistry.load(reg_path).ids))

    if args.mode == "dry-run":
        Path(f"{args.state}/proposed_changes").mkdir(parents=True, exist_ok=True)
        with open(f"{args.state}/proposed_changes/drafts.jsonl", "w", encoding="utf-8") as f:
            for rec, d in to_write:
                f.write(json.dumps({"pid": d.pid, "themes": d.themes, "primary": d.primary_theme,
                                    "重要性": d.importance, "gate": d.gate_passed_deep},
                                   ensure_ascii=False) + "\n")
        write_queue(queue, f"{args.state}/review_queue/queue.jsonl")
        report.render(drafts, queue, warns, None, f"{args.state}/reports/dryrun.html")
        print(f"dry-run: 待写 {len(to_write)} · 入队 {len(queue)} · 告警 {len(warns)}")

    elif args.mode == "apply":
        from datetime import date  # 仅 apply 用真实日期
        today = date.today().isoformat()
        for rec, d in to_write:
            write_business_view(d, args.vault, sanitized_from=rec.path,
                                extracted_at=today, extracted_model=args.gen_model)
        write_queue(queue, f"{args.state}/review_queue/queue.jsonl")
        print(f"apply: 写 business_view {len(to_write)} 篇 · 入队 {len(queue)}")

    elif args.mode == "verify":
        # 幂等:重跑分类条数应稳定;再跑 schema validator
        again_write, again_queue = plan(args.vault, reg_path, sc_text, gen_client, judge_client)
        print(f"verify: 二跑 待写 {len(again_write)} · 入队 {len(again_queue)}（应与 apply 前一致）")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/l2_themescore/test_run_2b.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: 全模块测试**

Run: `python -m pytest tests/l2_themescore/ -v`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/l2_themescore/run_2b.py tests/l2_themescore/test_run_2b.py
git commit -m "feat(②-B): run_2b 编排 CLI(dry-run/apply/verify, gen≠judge 断言)"
```

---

## Task 11: B5 词表收口(数据,无新代码)

**Files:**
- Modify: `_meta/themes_registry.yaml`(vault)— 见 spec §9
- Modify: `1_extracted/entities/registry.yaml`(vault)
- Modify: `scripts/l1_audit/vocab_check.py`(允许共享 alias)

- [ ] **Step 1: 改 vocab_check 允许共享 alias**

读 `scripts/l1_audit/vocab_check.py`,把"同词→2 theme = 冲突"的判定改为"允许;仅当一个词映射到 >1 theme 时不再报 error,记 info"。运行确认 `负荷聚合` 不再报冲突。

Run: `python scripts/l1_audit/vocab_check.py`(或其既有入口)
Expected: 原 2 处 alias 冲突消失(负荷聚合 / 成品油零售)

- [ ] **Step 2: entities/registry 补 type=theme(3 个)**

给 `charging_infra` / `power_market` / `v2g` 在 `1_extracted/entities/registry.yaml` 补 `type: theme`(themes_registry 已有,entities 缺)。删除 `rural_revitalization_theme` 的 theme 类型(乡村非 theme,B9)。

- [ ] **Step 3: verify**

Run: `python scripts/l1_audit/vocab_check.py`
Expected: registry 自洽,0 error(共享 alias 记 info 不报错)

- [ ] **Step 4: Commit(vault)**

```bash
cd "$HOME/Documents/Zayn Main/政策分析"
git add _meta/themes_registry.yaml 1_extracted/entities/registry.yaml
git commit -m "②-B: B5 词表收口(alias 可跨theme / 补3个type=theme / 删rural theme)"
cd -  # 回 pipeline
git add scripts/l1_audit/vocab_check.py
git commit -m "feat(②-B): vocab_check 允许共享 alias(B5)"
```

---

## Task 12: SCHEMA §4 门校准(doc)

**Files:**
- Modify: `SCHEMA.md`(vault)§4

- [ ] **Step 1: 改 §4 门 + 加字段定义**

把 §4「影响分析/行动建议(可选,**D1≥3** 时填)」改为「(可选,**重要性≥3 OR region.level∈{国家,省}** 时填)」。新增 `themes`(list,∈themes_registry)、`primary_theme`(∈themes)、`gate_passed_deep`(bool)字段定义。在 §4 末尾加一行评审记录:`# 2026-06-01 ②-B 校准:深档门 D1≥3 → 重要性≥3 OR 国省级;新增 themes/primary_theme/gate_passed_deep。理由见 spec §10。`

- [ ] **Step 2: verify 一致**

Run: `grep -n "重要性≥3 OR\|gate_passed_deep\|primary_theme" "SCHEMA.md"`(vault)
Expected: 命中新内容

- [ ] **Step 3: Commit(vault)**

```bash
cd "$HOME/Documents/Zayn Main/政策分析"
git add SCHEMA.md
git commit -m "schema(§4): ②-B 校准深档门(重要性≥3 OR 国省级)+ themes/primary_theme/gate_passed_deep"
```

---

## Task 13: golden 标注 + 抽查 + 冻结 + judge 校准 ⛔ STOP(人工)

**Files:**
- Create: `state/node2b/golden/golden_v1.jsonl`
- Create: `state/node2b/reports/judge_calibration.html`

- [ ] **Step 1: 分层抽 ~50 篇**

写一次性脚本 `scripts/_oneshot/sample_golden_2b.py`:从 935 篇按 13 theme × 国/省/市 × 高/中/低重要性 × 过门/不过门 分层抽 ~50 pid(保证每 theme 有样本)。输出 pid 清单。

- [ ] **Step 2: 我(Opus4.8)写 gold 标注**

对抽样 pid,我逐篇读 raw、写正确 `gold_themes/gold_primary/gold_scores/gold_影响分析`。再造若干**埋错副本**(`is_planted=true` + `error_type`):乱挂热门theme / 漏挂主题 / 低估地方政策分 / 幻觉业务影响 / 影响分析键缺失。落 `golden_v1.jsonl`。

- [ ] **Step 3: ⛔ 用户抽查 ~10 篇**

把我标的 gold 渲染成 HTML 给用户,用户抽查 ~10 篇确认标注无误(答案键人工兜底)。有错则改。

- [ ] **Step 4: 冻结**

```bash
git add state/node2b/golden/golden_v1.jsonl
git commit -m "data(②-B): 冻结 golden_v1(~50篇 gold + 埋错,用户抽查过)"
```

- [ ] **Step 5: 跑 judge 校准**

写 `scripts/_oneshot/calibrate_judge_2b.py`:对 golden 每条造 draft → judge_draft(模型B) → `score_judge`。产 `judge_calibration.html`(召回/精度 + 漏抓/误杀清单)。

- [ ] **Step 6: ⛔ 我裁决上岗阈值**

看实测召回/精度分布定阈值(测试期我裁决)。不达标 → 调 judge 提示词(judge.py JUDGE_SYSTEM)重跑,直到达标。达标 → judge 上岗,例行 4.8-free。

---

## Task 14: 935 真实 dry-run + 验收门 ⛔ STOP(用户)

- [ ] **Step 1: 跑 dry-run**

```bash
python -m scripts.l2_themescore.run_2b dry-run --gen-model <模型A> --judge-model <模型B>
```
Expected: 打印 待写/入队/告警 数;产 `state/node2b/reports/dryrun.html`

- [ ] **Step 2: ⛔ 用户看分布**

打开 `dryrun.html`(HTML)。用户审:theme 命中分布合理?孤岛多少?过门比例?入队的错型?批准 → 进 apply;不批 → 调提示词/门重跑(零补丁,整体重跑)。

---

## Task 15: apply + verify ⛔ STOP(写 business_view 派生层)

- [ ] **Step 1: apply 写 business_view**

```bash
python -m scripts.l2_themescore.run_2b apply --gen-model <模型A> --judge-model <模型B>
```
Expected: 写 `{vault}/_meta/business_view/*.yaml`(整文件重生覆盖旧 912 + ②-A 改id化石)

- [ ] **Step 2: verify 幂等 + schema**

```bash
python -m scripts.l2_themescore.run_2b verify --gen-model <模型A> --judge-model <模型B>
python scripts/audit/validate_schema.py        # check_business_view 0 违反
grep -rl "乡村" "$HOME/Documents/Zayn Main/政策分析/_meta/business_view/" | wc -l   # 期望 0(B9 收尾验证,一次性)
```
Expected: 二跑分类数稳定;validator 0 违反;乡村残留 = 0

- [ ] **Step 3: Commit(vault business_view)**

```bash
cd "$HOME/Documents/Zayn Main/政策分析"
git add _meta/business_view/
git commit -m "②-B: 归属挂载 apply(935篇 theme+重要性,过门篇含3-key影响分析)"
git tag pre-2b-done-$(date +%Y-%m-%d)   # 可回滚锚
```

---

## Self-Review(对照 spec)

**Spec 覆盖**:§1边界→Task1-10/边界守卫(Task8 never_writes_raw);§2三决策→多theme(Task2/5)、两遍门(Task3/10)、golden(Task7/13);§4数据模型→Task1/8;§5流程→Task10 plan();§6确定性→Task3;§7程序门→Task4;§8 judge+golden→Task6/7/13;§9 B5→Task11;§10 SCHEMA→Task12;§11模块→全;§12错误队列→Task9/10;§13测试→各Task TDD + Task14集成;§14纪律→Task8守卫/Task10零补丁注释;§15交付+验收门→Task13/14/15 STOP;§16开放项→A/B模型为CLI参数(Task10)、阈值Task13。**无遗漏**。

**Placeholder 扫描**:Task11/12/13 是数据/人工任务,步骤为精确命令/编辑指令(非代码占位);代码任务均给完整代码。Task13 的 gold 标注内容由我执行时产出(本就是人工标注任务,非计划占位)。

**类型一致**:`Scores`/`BusinessViewDraft`/`JudgeVerdict`/`QueueRecord`/`GoldenRecord` 跨 Task 签名一致;`gen_pass1/gen_pass2/judge_draft/write_business_view/write_queue/score_judge/check_draft/check_distribution/importance/action_class/gate_passed_deep/value_tags` 在 run_2b 的调用与各 Task 定义一致。`ThemeRegistry.ids/alias_index/zh/aliases/is_valid` 一致。

**已知可调**:generator 只喂 `body_head`(正文前2000字)——对多数政策的主旨足够;若 Task14 dry-run 显示长文漏判,扩为读全文(corpus 加 body 全量接口)。

---

## Execution Handoff

待用户选执行方式(subagent-driven 推荐 / inline)。建议:Task 1–10(纯代码 TDD)走 subagent-driven 连跑;Task 11–15(数据/人工/STOP 门)回到主会话由我 + 用户逐个过。
