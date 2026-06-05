# ③-C 语义政策关系生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 spec `2026-06-04-analysis-semantic-relations-design.md`(含 6/5 修订 §12-§14)实现 ③-C 语义关系 **preview**:程序出收敛候选 → 受限模型判定 → 程序门 → accepted / 人工池,只 preview 不 apply。

**Architecture:** 镜像 ③-B 模块结构(`scripts/analysis_semantic_relations/{models,candidates,judge,program_gate,report,run}.py` + `tests/`)。候选层确定性(读 836 篇 business_view 的 theme/importance + raw frontmatter 的 region/issuer/date + ③-B 高精度关系当 basis 信号),按 §12 收敛(top-k=8/±3年/aligns跨地区)、§14 对称规范化;判定层用普通模型(MiniMax gen 端不参与;judge 用 deepseek-v4-flash,与 ②-B 同端点),只输出 accept/reject/manual_review;程序门挡 schema/白名单/证据/方向矛盾;输出落 `state/analysis_layer/sem_preview_YYYYMMDD/`。judge 先经 ③-C golden(~40对)校准达标才上岗。

**Tech Stack:** Python3.9 stdlib + PyYAML;`scripts.l1_audit.corpus.load_policies`(raw)、`scripts.common.llm`(OpenAICompatClient,judge);pytest。无新依赖。

**Scope / 非目标:**
- 只 preview;**不写 vault、不写 raw、不 apply、不消费 review queue/blocked signals**(spec §10 验收门)。
- **Lever B 不在本计划**:它是 ③/④ 消费时的下游纳入门(analysis-layer §10.5),③-C accepted 关系产出后才在 ④ 选择阶段实现;此处仅产出关系,不做消费门。
- `conflicts_with` 默认不自动生成 accepted(spec §4.3),仅可作人工池提示——本计划候选层不生成它。

**约定:** 工作在 pipeline 主 checkout(项目惯例:main + tag,非 per-feature worktree)。模型经环境变量接线(同 ②-B):`OPENAI_BASE_URL=https://api.deepseek.com` / `OPENAI_API_KEY=$DEEPSEEK_API_KEY` / judge model `deepseek-v4-flash`。凭据在 `~/.config/policy-pipeline/models.env`(out-of-git)。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `scripts/analysis_semantic_relations/__init__.py` | 包标记 |
| `scripts/analysis_semantic_relations/models.py` | `SemanticCandidate` / `SemanticJudgment` dataclass + `canonical_pair` + `candidate_id` |
| `scripts/analysis_semantic_relations/loaders.py` | 载入 business_view(theme/importance/primary)+ raw frontmatter(region/issuer/date/title)+ ③-B 高精度关系 |
| `scripts/analysis_semantic_relations/candidates.py` | 确定性候选生成(4 类关系规则 + §12 top-k/时间窗/aligns跨地区 + §14 对称规范化) |
| `scripts/analysis_semantic_relations/judge.py` | `SEMANTIC_RELATION_JUDGE_SYSTEM` + `judge_candidate(client, cand, ctx)` |
| `scripts/analysis_semantic_relations/program_gate.py` | schema/白名单/证据/manual_review/对称去重/方向矛盾 检查 |
| `scripts/analysis_semantic_relations/report.py` | 中文 preview HTML |
| `scripts/analysis_semantic_relations/run.py` | preview 编排:candidates → judge → gate → 输出分层 + summary + report |
| `scripts/_oneshot/build_3c_golden.py` | ③-C golden(~40对分层抽样 + 埋错位)→ `state/node3c/golden/` |
| `scripts/_oneshot/calibrate_3c_judge.py` | judge 校准(镜像 `calibrate_judge_2b.py`)→ recall/precision 报告 |
| `tests/analysis_semantic_relations/test_models.py` `test_candidates.py` `test_program_gate.py` `test_run.py` | 单测 |

输入(只读):vault `_meta/business_view/*.yaml`、`0_raw/policies/*.md`、③-B `state/analysis_layer/preview_*/high_precision_relation_candidates.jsonl`、`_meta/themes_registry.yaml`。
输出:`state/analysis_layer/sem_preview_YYYYMMDD/{semantic_relation_candidates.jsonl, accepted_semantic_relations.jsonl, manual_review_queue.jsonl, semantic_relation_summary.json, reports/semantic_relation_preview.html}`。

关系白名单(本计划生成):`derives_from`(有向)、`extends`(有向)、`iterates`(有向)、`aligns_with`(对称)。

---

## Task 1: 数据模型 + 规范化

**Files:**
- Create: `scripts/analysis_semantic_relations/__init__.py`(内容:单空行)
- Create: `scripts/analysis_semantic_relations/models.py`
- Test: `tests/analysis_semantic_relations/__init__.py`(空)、`tests/analysis_semantic_relations/test_models.py`

- [ ] **Step 1: 写失败测试** `tests/analysis_semantic_relations/test_models.py`

```python
from scripts.analysis_semantic_relations.models import (
    SemanticCandidate, canonical_pair, candidate_id, DIRECTED, SYMMETRIC,
)


def test_canonical_pair_symmetric_sorts_by_pid():
    assert canonical_pair("P_B", "P_A", "aligns_with") == ("P_A", "P_B")
    # 有向关系保留原方向
    assert canonical_pair("P_B", "P_A", "derives_from") == ("P_B", "P_A")


def test_candidate_id_stable_and_direction_aware():
    a = candidate_id("P_A", "P_B", "derives_from")
    assert a == candidate_id("P_A", "P_B", "derives_from")
    assert a != candidate_id("P_B", "P_A", "derives_from")  # 有向:换向不同 id
    # 对称:两向同 id(因 canonical_pair 已排序)
    assert candidate_id(*canonical_pair("P_B", "P_A", "aligns_with"), "aligns_with") == \
           candidate_id(*canonical_pair("P_A", "P_B", "aligns_with"), "aligns_with")


def test_relation_sets():
    assert "aligns_with" in SYMMETRIC
    assert {"derives_from", "extends", "iterates"} <= DIRECTED
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_models.py -v`
Expected: FAIL（ModuleNotFoundError: scripts.analysis_semantic_relations.models）

- [ ] **Step 3: 写实现** `scripts/analysis_semantic_relations/models.py`

```python
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field, asdict

SYMMETRIC = {"aligns_with", "conflicts_with"}
DIRECTED = {"derives_from", "extends", "iterates", "supersedes", "cites_basis", "references"}
SCHEMA_VERSION = "analysis_semantic_relation_preview.v1"


def canonical_pair(from_id: str, to_id: str, rel: str) -> tuple[str, str]:
    """对称关系按 pid 字典序规范化(§14);有向关系保留方向。"""
    if rel in SYMMETRIC and from_id > to_id:
        return to_id, from_id
    return from_id, to_id


def candidate_id(from_id: str, to_id: str, rel: str) -> str:
    raw = "|".join([from_id, to_id, rel])
    return "SRC_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SemanticCandidate:
    from_id: str
    to_id: str
    rel: str
    candidate_basis: list[str]          # ["basis_relation_present","same_theme",...]
    evidence: dict                       # {from_title,to_title,from_window,to_window,theme_context}
    symmetric: bool = False

    def cid(self) -> str:
        return candidate_id(self.from_id, self.to_id, self.rel)

    def to_row(self) -> dict:
        return {
            "candidate_id": self.cid(),
            "schema_version": SCHEMA_VERSION,
            "from": self.from_id, "to": self.to_id, "rel": self.rel,
            "symmetric": self.symmetric,
            "candidate_basis": list(self.candidate_basis),
            "evidence": self.evidence,
            "source": "scripts/analysis_semantic_relations/run.py",
        }


@dataclass(frozen=True)
class SemanticJudgment:
    candidate_id: str
    decision: str        # accept | reject | manual_review
    confidence: float
    reason: str
    model: str
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/analysis_semantic_relations/__init__.py scripts/analysis_semantic_relations/models.py tests/analysis_semantic_relations/
git commit -m "feat(③-C): models + 对称规范化/候选id"
```

---

## Task 2: 输入载入(business_view + raw 元数据 + ③-B 关系)

**Files:**
- Create: `scripts/analysis_semantic_relations/loaders.py`
- Test: `tests/analysis_semantic_relations/test_loaders.py`

载入产物 = 每篇政策一个 `PolicyView`:`pid, title, region_level, region_name, issuer, year, themes, primary_theme, importance`。region/issuer/date/title 取自 raw frontmatter(用 `scripts.l1_audit.corpus.load_policies`,其 `rec.raw_fm` 是完整 frontmatter、`rec.pid/rec.title`);themes/primary/importance 取自 vault `_meta/business_view/{pid}.yaml`。无 business_view 的政策(入队的 100 篇)`themes=[]`,候选层自然不会把它们当主题簇成员。

- [ ] **Step 1: 写失败测试** `tests/analysis_semantic_relations/test_loaders.py`

```python
from pathlib import Path
from scripts.analysis_semantic_relations.loaders import (
    PolicyView, load_policy_views, load_hpr_basis_pairs, _year_of,
)


def test_year_parsing():
    assert _year_of("2023-05-01") == 2023
    assert _year_of("2023年5月") == 2023
    assert _year_of("") is None


def test_policy_view_from_fixture(tmp_path):
    # business_view fixture
    bv = tmp_path / "_meta" / "business_view"; bv.mkdir(parents=True)
    (bv / "P_X.yaml").write_text(
        "pid: P_X\nthemes: [power_market]\nprimary_theme: power_market\n重要性: 4\n",
        encoding="utf-8")
    views = load_policy_views(
        policies=[PolicyView(pid="P_X", title="某电力市场方案", region_level="省",
                             region_name="广东", issuer="广东省发改委", year=2023,
                             themes=[], primary_theme="", importance=None)],
        vault=tmp_path)
    v = views["P_X"]
    assert v.themes == ["power_market"] and v.primary_theme == "power_market" and v.importance == 4


def test_hpr_basis_pairs(tmp_path):
    p = tmp_path / "hpr.jsonl"
    p.write_text('{"from":"P_LOCAL","to":"P_NAT","rel":"cites_basis"}\n'
                 '{"from":"P_A","to":"P_B","rel":"references"}\n', encoding="utf-8")
    pairs = load_hpr_basis_pairs(p)
    assert ("P_LOCAL", "P_NAT") in pairs  # cites_basis 计入 basis
    assert ("P_A", "P_B") in pairs        # references 也计入(弱 basis 信号)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_loaders.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 写实现** `scripts/analysis_semantic_relations/loaders.py`

```python
from __future__ import annotations
import json, re
from dataclasses import dataclass, replace
from pathlib import Path
import yaml
from scripts.l1_audit.corpus import load_policies

BASIS_RELS = {"cites_basis", "references"}  # ③-B 里指向上位文件的信号


@dataclass(frozen=True)
class PolicyView:
    pid: str
    title: str
    region_level: str
    region_name: str
    issuer: str
    year: int | None
    themes: list
    primary_theme: str
    importance: int | None


def _year_of(date_str: str) -> int | None:
    m = re.search(r"(19|20)\d{2}", str(date_str or ""))
    return int(m.group(0)) if m else None


def _raw_views(vault: Path) -> list[PolicyView]:
    out = []
    for rec in load_policies(f"{vault}/0_raw/policies"):
        fm = rec.raw_fm or {}
        region = fm.get("region") or {}
        out.append(PolicyView(
            pid=rec.pid, title=rec.title,
            region_level=str(region.get("level", "")),
            region_name=str(region.get("name", "")),
            issuer=str(fm.get("issuer", "")),
            year=_year_of(fm.get("date", "")),
            themes=[], primary_theme="", importance=None))
    return out


def load_policy_views(policies: list[PolicyView] | None = None, vault: Path = None) -> dict:
    """policies 可注入(测试);否则从 raw 读。再用 business_view 覆盖 themes/primary/importance。"""
    base = policies if policies is not None else _raw_views(Path(vault))
    bv_dir = Path(vault) / "_meta" / "business_view"
    by_pid = {}
    for v in base:
        doc = {}
        f = bv_dir / f"{v.pid}.yaml"
        if f.exists():
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        by_pid[v.pid] = replace(
            v,
            themes=list(doc.get("themes", []) or []),
            primary_theme=str(doc.get("primary_theme", "") or ""),
            importance=doc.get("重要性"))
    return by_pid


def load_hpr_basis_pairs(hpr_path: Path) -> set:
    """从 ③-B 高精度候选读 (from,to) 对,作为 derives_from 的 basis 信号。"""
    pairs = set()
    if not Path(hpr_path).exists():
        return pairs
    for line in Path(hpr_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("rel") in BASIS_RELS:
            pairs.add((row.get("from"), row.get("to")))
    return pairs
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_loaders.py -v`
Expected: PASS (3 passed)。⚠ `test_policy_view_from_fixture` 注入 policies,不触发 raw 加载。

- [ ] **Step 5: 提交**

```bash
git add scripts/analysis_semantic_relations/loaders.py tests/analysis_semantic_relations/test_loaders.py
git commit -m "feat(③-C): 输入载入器(business_view+raw+③-B basis)"
```

---

## Task 3: 确定性候选生成(§4 规则 + §12 收敛 + §14 对称)

**Files:**
- Create: `scripts/analysis_semantic_relations/candidates.py`
- Test: `tests/analysis_semantic_relations/test_candidates.py`

规则(spec §4.1/§4.2 + §12 边界):
- `iterates`(有向,旧→新):同 issuer + 同 primary_theme + year 递增 + |Δyear|≤3。
- `extends`(有向,旧→新):同 primary_theme + year 递增 + |Δyear|≤3 + 新篇标题含范围扩展词(扩大/扩围/推广/全面实施/由试点)。
- `derives_from`(有向,低→高):`(from,to)` ∈ ③-B basis 对 **且** from 的 region_level 低于 to(地方<省<国)+ 主题相同/相邻。
- `aligns_with`(对称):同 primary_theme + |Δyear|≤3 + **跨地区或跨部门**(region_name 或 issuer 不同)+ 不存在 ③-B 引用/依据关系。
- **§12 收敛**:对每个 (源篇, 关系) 只保留按相似度排序的 **top-k=8**;时间窗 ±3 年硬上限。
- **§14**:对称关系用 `canonical_pair` 去重。

`REGION_RANK = {"国":3,"省":2,"市":1,"区县":0,"":0}`(取 region_level 首字匹配)。

- [ ] **Step 1: 写失败测试** `tests/analysis_semantic_relations/test_candidates.py`

```python
from scripts.analysis_semantic_relations.loaders import PolicyView
from scripts.analysis_semantic_relations.candidates import generate_candidates, TOP_K, WINDOW_YEARS


def V(pid, year, theme, level="省", region="广东", issuer="发改委", title="方案"):
    return PolicyView(pid=pid, title=title, region_level=level, region_name=region,
                      issuer=issuer, year=year, themes=[theme], primary_theme=theme,
                      importance=3)


def test_iterates_same_issuer_theme_year_increasing():
    views = {"P1": V("P1", 2020, "power_market"), "P2": V("P2", 2022, "power_market")}
    cands = generate_candidates(views, basis_pairs=set())
    iters = [c for c in cands if c.rel == "iterates"]
    assert any(c.from_id == "P1" and c.to_id == "P2" for c in iters)  # 旧→新


def test_aligns_requires_cross_region_symmetric_dedup():
    views = {"A": V("A", 2021, "power_market", region="广东"),
             "B": V("B", 2021, "power_market", region="江苏")}
    cands = generate_candidates(views, basis_pairs=set())
    aligns = [c for c in cands if c.rel == "aligns_with"]
    assert len(aligns) == 1                      # 对称去重:只一条
    assert aligns[0].symmetric is True
    assert (aligns[0].from_id, aligns[0].to_id) == ("A", "B")  # 字典序


def test_aligns_skipped_same_region():
    views = {"A": V("A", 2021, "power_market", region="广东", issuer="发改委"),
             "B": V("B", 2021, "power_market", region="广东", issuer="发改委")}
    cands = generate_candidates(views, basis_pairs=set())
    assert not [c for c in cands if c.rel == "aligns_with"]  # 同地区同部门→不生成 aligns


def test_derives_from_needs_basis_and_lower_region():
    views = {"LOCAL": V("LOCAL", 2022, "power_market", level="市", region="深圳"),
             "NAT": V("NAT", 2021, "power_market", level="国", region="全国", issuer="发改委")}
    # 有 basis 对(local 引 nat)→ derives_from local→nat
    cands = generate_candidates(views, basis_pairs={("LOCAL", "NAT")})
    assert any(c.rel == "derives_from" and c.from_id == "LOCAL" and c.to_id == "NAT" for c in cands)
    # 无 basis 对 → 不生成 derives_from
    assert not [c for c in generate_candidates(views, basis_pairs=set()) if c.rel == "derives_from"]


def test_window_caps_year_gap():
    views = {"P1": V("P1", 2010, "power_market"), "P2": V("P2", 2022, "power_market")}
    cands = generate_candidates(views, basis_pairs=set())
    assert not [c for c in cands if c.rel in {"iterates", "aligns_with"}]  # Δ=12 > 3


def test_topk_bound():
    base = {f"S{i}": V(f"S{i}", 2021, "power_market", region=f"r{i}") for i in range(20)}
    src = {"SRC": V("SRC", 2022, "power_market", region="rc")}
    cands = generate_candidates({**base, **src}, basis_pairs=set())
    from_src = [c for c in cands if c.from_id == "SRC" or c.to_id == "SRC"]
    aligns_touching_src = [c for c in from_src if c.rel == "aligns_with"]
    assert len(aligns_touching_src) <= TOP_K
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_candidates.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 写实现** `scripts/analysis_semantic_relations/candidates.py`

```python
from __future__ import annotations
from .models import SemanticCandidate, canonical_pair
from .loaders import PolicyView

TOP_K = 8
WINDOW_YEARS = 3
REGION_RANK = {"国": 3, "省": 2, "市": 1, "区": 0, "县": 0, "": 0}
EXTEND_WORDS = ("扩大", "扩围", "推广", "全面实施", "由试点", "适用范围", "新增")


def _rank(level: str) -> int:
    return REGION_RANK.get((level or "")[:1], 0)


def _window_ok(a: PolicyView, b: PolicyView) -> bool:
    return a.year is not None and b.year is not None and abs(a.year - b.year) <= WINDOW_YEARS


def _evidence(a: PolicyView, b: PolicyView, basis: list) -> dict:
    return {"from_title": a.title, "to_title": b.title,
            "from_window": "", "to_window": "",
            "theme_context": [a.primary_theme] if a.primary_theme else []}


def _similarity(a: PolicyView, b: PolicyView) -> float:
    """确定性相似:同 primary 主题(基线)+ 标题字符重合,用于 top-k 排序。"""
    base = 1.0 if a.primary_theme and a.primary_theme == b.primary_theme else 0.0
    sa, sb = set(a.title), set(b.title)
    jacc = len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0
    return base + jacc


def generate_candidates(views: dict, basis_pairs: set) -> list:
    items = list(views.values())
    out: list[SemanticCandidate] = []
    seen_symmetric = set()
    for a in items:
        if not a.primary_theme:
            continue
        scored = []  # (sim, b, rel, basis_tags)
        for b in items:
            if a.pid == b.pid or not b.primary_theme:
                continue
            same_theme = a.primary_theme == b.primary_theme
            # iterates: 同 issuer + 同主题 + 旧(a)→新(b)
            if same_theme and a.issuer and a.issuer == b.issuer and _window_ok(a, b) \
                    and a.year is not None and b.year is not None and a.year < b.year:
                scored.append((_similarity(a, b), b, "iterates", ["same_issuer", "same_theme", "year_increasing"]))
            # extends: 同主题 + 旧→新 + 新篇范围扩展词
            if same_theme and _window_ok(a, b) and a.year is not None and b.year is not None \
                    and a.year < b.year and any(w in b.title for w in EXTEND_WORDS):
                scored.append((_similarity(a, b), b, "extends", ["same_theme", "year_increasing", "scope_extend_word"]))
            # derives_from: ③-B basis 对 + from 区划低于 to + 主题同
            if (a.pid, b.pid) in basis_pairs and _rank(a.region_level) < _rank(b.region_level) and same_theme:
                scored.append((_similarity(a, b) + 2, b, "derives_from", ["basis_relation_present", "lower_region_level", "same_theme"]))
            # aligns_with: 同主题 + 跨地区/跨部门 + 窗内 + 无引用关系
            if same_theme and _window_ok(a, b) \
                    and (a.region_name != b.region_name or a.issuer != b.issuer) \
                    and (a.pid, b.pid) not in basis_pairs and (b.pid, a.pid) not in basis_pairs:
                scored.append((_similarity(a, b), b, "aligns_with", ["same_theme", "cross_region_or_dept"]))
        # §12 top-k(按 sim 降序,每源篇上限)
        scored.sort(key=lambda x: (-x[0], x[1].pid))
        kept = 0
        for sim, b, rel, tags in scored:
            if kept >= TOP_K:
                break
            if rel == "aligns_with":
                fp, tp = canonical_pair(a.pid, b.pid, rel)
                key = (fp, tp, rel)
                if key in seen_symmetric:
                    continue
                seen_symmetric.add(key)
                out.append(SemanticCandidate(fp, tp, rel, tags, _evidence(a, b, tags), symmetric=True))
            else:
                out.append(SemanticCandidate(a.pid, b.pid, rel, tags, _evidence(a, b, tags)))
            kept += 1
    return sorted(out, key=lambda c: (c.rel, c.from_id, c.to_id))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_candidates.py -v`
Expected: PASS (6 passed)。若 `test_topk_bound` 偶发,确认 top-k 对 aligns 也生效。

- [ ] **Step 5: 提交**

```bash
git add scripts/analysis_semantic_relations/candidates.py tests/analysis_semantic_relations/test_candidates.py
git commit -m "feat(③-C): 确定性候选生成(§4规则+§12收敛+§14对称)"
```

---

## Task 4: 程序门(schema/白名单/证据/manual_review/方向矛盾)

**Files:**
- Create: `scripts/analysis_semantic_relations/program_gate.py`
- Test: `tests/analysis_semantic_relations/test_program_gate.py`

门规则(spec §5.3 + §14):
- 候选行缺 `from/to/rel/evidence/candidate_basis` → 失败。
- `rel` 不在白名单 → 失败。
- 判定行 `decision` ∉ {accept,reject,manual_review} → 失败。
- `manual_review`/`reject` **不得进 accepted**。
- accepted 集中:对称关系无重复(canonical 唯一);**方向矛盾**(同一对 pid 出现互斥有向关系)→ 涉及的候选改判 manual_review,不进 accepted。

- [ ] **Step 1: 写失败测试** `tests/analysis_semantic_relations/test_program_gate.py`

```python
from scripts.analysis_semantic_relations.program_gate import check_candidate_row, partition_by_decision, WHITELIST


def test_schema_and_whitelist():
    ok = {"from": "A", "to": "B", "rel": "iterates", "evidence": {}, "candidate_basis": ["x"]}
    assert check_candidate_row(ok) == []
    assert check_candidate_row({**ok, "rel": "conflicts_with"})  # 非白名单→报错
    assert check_candidate_row({k: v for k, v in ok.items() if k != "evidence"})  # 缺字段


def test_partition_excludes_nonaccept():
    cands = [{"candidate_id": "c1", "from": "A", "to": "B", "rel": "iterates"},
             {"candidate_id": "c2", "from": "C", "to": "D", "rel": "aligns_with", "symmetric": True}]
    judg = {"c1": "accept", "c2": "manual_review"}
    accepted, manual = partition_by_decision(cands, judg)
    assert [c["candidate_id"] for c in accepted] == ["c1"]
    assert [c["candidate_id"] for c in manual] == ["c2"]


def test_direction_conflict_to_manual():
    cands = [{"candidate_id": "c1", "from": "A", "to": "B", "rel": "derives_from"},
             {"candidate_id": "c2", "from": "B", "to": "A", "rel": "iterates"}]
    judg = {"c1": "accept", "c2": "accept"}
    accepted, manual = partition_by_decision(cands, judg)
    assert accepted == []                      # 互斥有向 → 都不进 accepted
    assert {c["candidate_id"] for c in manual} == {"c1", "c2"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_program_gate.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 写实现** `scripts/analysis_semantic_relations/program_gate.py`

```python
from __future__ import annotations
from collections import defaultdict

WHITELIST = {"derives_from", "extends", "iterates", "aligns_with"}
REQUIRED = ("from", "to", "rel", "evidence", "candidate_basis")


def check_candidate_row(row: dict) -> list:
    viol = []
    for key in REQUIRED:
        if key not in row:
            viol.append(f"missing:{key}")
    if row.get("rel") not in WHITELIST:
        viol.append(f"rel_not_whitelisted:{row.get('rel')}")
    return viol


def partition_by_decision(candidates: list, judgments: dict) -> tuple:
    """judgments: candidate_id -> decision。返回 (accepted, manual)。
    只有 accept 进 accepted;manual_review/reject 进 manual;方向矛盾对降级 manual。"""
    accepted, manual = [], []
    for c in candidates:
        d = judgments.get(c["candidate_id"], "manual_review")
        (accepted if d == "accept" else manual).append(c)
    # 方向矛盾:同一对 pid(无序)在 accepted 里有 >1 种有向关系 → 全降级 manual
    by_pair = defaultdict(list)
    for c in accepted:
        by_pair[frozenset([c["from"], c["to"]])].append(c)
    conflicted = set()
    for pair, rows in by_pair.items():
        rels = {r["rel"] for r in rows if not r.get("symmetric")}
        if len(rels) > 1:
            conflicted.update(id(r) for r in rows if not r.get("symmetric"))
    if conflicted:
        keep, demote = [], []
        for c in accepted:
            (demote if id(c) in conflicted else keep).append(c)
        accepted, manual = keep, manual + demote
    return accepted, manual
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_program_gate.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/analysis_semantic_relations/program_gate.py tests/analysis_semantic_relations/test_program_gate.py
git commit -m "feat(③-C): 程序门(schema/白名单/方向矛盾→人工池)"
```

---

## Task 5: 受限判定 judge(prompt + 调用)

**Files:**
- Create: `scripts/analysis_semantic_relations/judge.py`
- Test: `tests/analysis_semantic_relations/test_judge.py`

judge 用普通模型(deepseek-v4-flash)只对**给定候选对**判 `accept|reject|manual_review`,不得全库自由联想(spec §5.2/§7)。输入只给:关系类型定义、双方标题、证据窗口、②归属摘要、禁止事项。复用 `scripts.common.llm.OpenAICompatClient` 与 ②-B 同端点。

- [ ] **Step 1: 写失败测试** `tests/analysis_semantic_relations/test_judge.py`

```python
from scripts.analysis_semantic_relations.judge import judge_candidate, SEMANTIC_RELATION_JUDGE_SYSTEM


class FakeClient:
    def __init__(self, payload): self.payload = payload; self.calls = []
    def complete(self, system, user, max_tokens=1024):
        self.calls.append((system, user)); return self.payload


def test_judge_parses_decision():
    c = FakeClient('{"decision":"accept","confidence":0.8,"reason":"地方落实上级且主题一致"}')
    v = judge_candidate(c, {"from": "P_L", "to": "P_N", "rel": "derives_from",
                            "evidence": {"from_title": "x", "to_title": "y"}})
    assert v.decision == "accept" and 0 <= v.confidence <= 1


def test_judge_non_json_is_manual_review():
    v = judge_candidate(FakeClient("不是JSON"), {"from": "A", "to": "B", "rel": "iterates", "evidence": {}})
    assert v.decision == "manual_review"   # 解析失败→保守进人工池(不静默 accept)


def test_prompt_forbids_free_association():
    assert "只判断" in SEMANTIC_RELATION_JUDGE_SYSTEM and "不得" in SEMANTIC_RELATION_JUDGE_SYSTEM
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_judge.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 写实现** `scripts/analysis_semantic_relations/judge.py`

```python
from __future__ import annotations
import json
from .models import SemanticJudgment

SEMANTIC_RELATION_JUDGE_SYSTEM = """你是政策关系审查员。给你两篇政策和一个候选关系类型,只判断该候选证据是否成立。
关系类型:
- derives_from:A(下级)落实/承接/细化 B(上级)。
- extends:后政策扩大了前政策的范围/试点。
- iterates:同机构同主题的年度续作/版本迭代。
- aligns_with:不同地区或部门在同一主题上方向对齐(不声明因果)。
规则:
1. 你只判断"这一对候选"是否成立,**不得**寻找新关系、不得改关系类型、不得全库联想。
2. 证据不足、模棱两可、或更像别的关系 → decision=manual_review(宁可进人工,不要硬判)。
3. 把 aligns 说成 derives、把无承接说成 derives = reject。
只输出 JSON:{"decision":"accept|reject|manual_review","confidence":0-1,"reason":"一句话"}
"""


def judge_candidate(client, cand: dict, max_tokens: int = 2048) -> SemanticJudgment:
    ev = cand.get("evidence", {})
    user = (f"关系类型:{cand['rel']}\n"
            f"A(from):{ev.get('from_title','')}\nB(to):{ev.get('to_title','')}\n"
            f"证据:from_window={ev.get('from_window','')} to_window={ev.get('to_window','')}\n"
            f"归属:theme_context={ev.get('theme_context',[])} 候选依据={cand.get('candidate_basis',[])}")
    txt = client.complete(system=SEMANTIC_RELATION_JUDGE_SYSTEM, user=user, max_tokens=max_tokens)
    cid = cand.get("candidate_id", f"{cand.get('from')}|{cand.get('to')}|{cand.get('rel')}")
    try:
        d = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        decision = d.get("decision", "manual_review")
        if decision not in {"accept", "reject", "manual_review"}:
            decision = "manual_review"
        return SemanticJudgment(cid, decision, float(d.get("confidence", 0.0)),
                                str(d.get("reason", "")), getattr(client, "model", "unknown"))
    except Exception:
        return SemanticJudgment(cid, "manual_review", 0.0, "judge 返回非JSON", getattr(client, "model", "unknown"))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_judge.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/analysis_semantic_relations/judge.py tests/analysis_semantic_relations/test_judge.py
git commit -m "feat(③-C): 受限判定 judge(prompt+解析,非JSON→人工池)"
```

---

## Task 6: preview 编排 run.py + report.py

**Files:**
- Create: `scripts/analysis_semantic_relations/report.py`、`scripts/analysis_semantic_relations/run.py`
- Test: `tests/analysis_semantic_relations/test_run.py`

`run_preview(vault, state, hpr_path, judge_client)`:载入 views + basis → 生成候选 → 每候选过 judge → program_gate.partition → 写 4 个产物 + summary + HTML。judge_client 可注入(测试用 Fake)。**不写 vault、不写 raw**。summary 记 candidate/accepted/manual 计数、按关系分布、model、`recommendation=preview_only_no_apply`、notes(no_vault_write/no_apply/...)。

- [ ] **Step 1: 写失败测试** `tests/analysis_semantic_relations/test_run.py`

```python
import json
from pathlib import Path
from scripts.analysis_semantic_relations.run import run_preview
from scripts.analysis_semantic_relations.loaders import PolicyView


class FakeClient:
    model = "fake"
    def complete(self, system, user, max_tokens=1024):
        return '{"decision":"accept","confidence":0.9,"reason":"ok"}'


def _views():
    return {"A": PolicyView("A", "甲", "省", "广东", "发改委", 2021, ["power_market"], "power_market", 3),
            "B": PolicyView("B", "乙", "省", "江苏", "发改委", 2021, ["power_market"], "power_market", 3)}


def test_run_preview_writes_outputs_no_vault(tmp_path, monkeypatch):
    import scripts.analysis_semantic_relations.run as runmod
    monkeypatch.setattr(runmod, "load_policy_views", lambda vault=None: _views())
    monkeypatch.setattr(runmod, "load_hpr_basis_pairs", lambda p: set())
    state = tmp_path / "sem"
    res = run_preview(vault=tmp_path / "vault", state=state, hpr_path=tmp_path / "none.jsonl",
                      judge_client=FakeClient())
    summ = json.loads((state / "semantic_relation_summary.json").read_text())
    assert summ["candidate_count"] >= 1 and summ["recommendation"] == "preview_only_no_apply"
    assert (state / "accepted_semantic_relations.jsonl").exists()
    assert not (tmp_path / "vault").exists()    # 绝不建/写 vault
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/analysis_semantic_relations/test_run.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 写实现**

`scripts/analysis_semantic_relations/report.py`(镜像 `analysis_high_precision_relations/report.py` 的中文 HTML 风格,函数 `render_preview_html(summary, accepted, manual, path) -> Path`,清楚标注"候选/accepted/待人工"三类、preview-only)。完整代码照搬 ③-B report.py 结构、替换表头与字段为关系三元组(from/to/rel/decision/reason)。

`scripts/analysis_semantic_relations/run.py`:

```python
from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path
from .loaders import load_policy_views, load_hpr_basis_pairs
from .candidates import generate_candidates
from .judge import judge_candidate
from . import program_gate
from .report import render_preview_html


def _write_jsonl(path: Path, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_preview(vault: Path, state: Path, hpr_path: Path, judge_client) -> dict:
    views = load_policy_views(vault=vault)
    basis = load_hpr_basis_pairs(hpr_path)
    candidates = [c.to_row() for c in generate_candidates(views, basis)]
    # 程序门:schema/白名单
    gate_fail = [c for c in candidates if program_gate.check_candidate_row(c)]
    valid = [c for c in candidates if not program_gate.check_candidate_row(c)]
    # 受限判定
    judgments = {}
    for c in valid:
        v = judge_candidate(judge_client, c)
        judgments[c["candidate_id"]] = v.decision
        c["confidence"] = v.confidence
        c["judge_reason"] = v.reason
        c["model"] = v.model
    accepted, manual = program_gate.partition_by_decision(valid, judgments)
    summary = {
        "candidate_count": len(candidates),
        "gate_failed": len(gate_fail),
        "accepted_count": len(accepted),
        "manual_count": len(manual),
        "accepted_by_relation": dict(Counter(c["rel"] for c in accepted)),
        "model": getattr(judge_client, "model", "unknown"),
        "recommendation": "preview_only_no_apply",
        "notes": ["no_vault_write", "no_raw_write", "no_apply",
                  "manual_review_not_in_accepted", "old_relations_not_used_as_accepted"],
    }
    _write_jsonl(state / "semantic_relation_candidates.jsonl", candidates)
    _write_jsonl(state / "accepted_semantic_relations.jsonl", accepted)
    _write_jsonl(state / "manual_review_queue.jsonl", manual)
    (state / "semantic_relation_summary.json").parent.mkdir(parents=True, exist_ok=True)
    (state / "semantic_relation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = render_preview_html(summary, accepted, manual, state / "reports" / "semantic_relation_preview.html")
    return {"summary": summary, "report_path": str(report)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("preview")
    p.add_argument("--vault", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--hpr", type=Path, required=True, help="③-B high_precision_relation_candidates.jsonl")
    p.add_argument("--judge-model", default="deepseek-v4-flash")
    args = ap.parse_args(argv)
    if args.mode == "preview":
        from scripts.common.llm import OpenAICompatClient
        client = OpenAICompatClient(model=args.judge_model,
                                    log_path=str(args.state / "judge_calls.jsonl"))
        res = run_preview(args.vault, args.state, args.hpr, client)
        print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/analysis_semantic_relations/ -v`
Expected: PASS（全模块单测绿）

- [ ] **Step 5: 提交**

```bash
git add scripts/analysis_semantic_relations/run.py scripts/analysis_semantic_relations/report.py tests/analysis_semantic_relations/test_run.py
git commit -m "feat(③-C): preview 编排 run+report(候选→judge→门→分层产物)"
```

---

## Task 7: ③-C golden 抽样器(§13)

**Files:**
- Create: `scripts/_oneshot/build_3c_golden.py`
- 产物:`state/node3c/golden/golden_pairs.jsonl`(~40 对,字段:from,to,rel,stratum,is_planted,planted_error_type,gold_decision)

逻辑:先跑确定性候选(generate_candidates)得到真实候选池;**分层抽样** ~30 对真实候选(覆盖 derives_from/extends/iterates/aligns 各 ≥5 + 易混对);再**人工/多模型标 gold_decision**(此脚本只产"待标"骨架 + 分层,真值标注在 Task 9 的工作流里);**埋错** ~10 对(把无关对标成有关系、aligns↔derives 混淆),`is_planted=true` + `planted_error_type`。冻结。镜像 ②-B `sample_golden_2b.py` 的分层+冻结写法。

- [ ] **Step 1-5(oneshot,无单测,但产物需自检)**
  - 写脚本:载入 views/basis → generate_candidates → 按 rel 分层各取 top-N 多样(不同地区/年份)→ 写骨架;追加埋错对。
  - 跑:`python3 -m scripts._oneshot.build_3c_golden --vault "$VAULT" --hpr <③-B jsonl> --out state/node3c/golden`
  - 自检:`python3 - <<'PY'` 断言 4 类关系各 ≥5、planted ≥8、无重复对。
  - 提交:`git add scripts/_oneshot/build_3c_golden.py && git add -f state/node3c/golden && git commit -m "feat(③-C Task7): golden 分层抽样+埋错骨架"`

---

## Task 8: golden 标注(多模型一致 + 用户裁分歧)

**Files:** 复用 ②-B 工作流模式 `scripts/_oneshot/wf_gold_label.js`(多模型独立标 + 一致性聚合),改造为关系判定版 `wf_3c_gold_label.js`:每对 × {opus,sonnet,haiku} 独立判 `accept/reject/manual` + 理由,脚本算一致性;low=分歧交用户裁。

- [ ] **Step 1:** 复制 `wf_gold_label.js` → `wf_3c_gold_label.js`,把"主题+6维分"换成"关系三元组判定";**把 ~40 对直接写死进脚本**(②-B 教训:别让载入器 agent 复述数组→StructuredOutput 空转)。
- [ ] **Step 2:** 跑(可外包独立 session,150-agent 量级会阻塞对话):`Workflow({scriptPath:".../wf_3c_gold_label.js"})` → `state/node3c/golden/labels_raw.json`。
- [ ] **Step 3:** 后处理:读 labels_raw → 渲 HTML 给用户裁 low/抽查 high → 写 `gold_decision` → 冻结 `golden_v1.jsonl`(每对:from,to,rel,gold_decision,is_planted,planted_error_type)。
- [ ] **Step 4:** 提交:`git add -f state/node3c/golden/golden_v1.jsonl && git add scripts/_oneshot/wf_3c_gold_label.js && git commit -m "feat(③-C Task8): golden_v1 冻结(多模型一致+用户裁)"`

**验证:** `golden_v1.jsonl` 行数 ≈ 40;`is_planted` 行有 `gold_decision=reject`(假关系应被拒);4 类关系齐。

---

## Task 9: judge 校准(达标才上岗,§13)

**Files:**
- Create: `scripts/_oneshot/calibrate_3c_judge.py`(镜像 `scripts/_oneshot/calibrate_judge_2b.py` 结构:读 golden_v1 → 对每对跑 `judge_candidate` → 比 gold_decision → 算 recall/precision → HTML)

判定维度:**"必须抓" = is_planted 的假关系/方向错**(judge 应 reject 或 manual);planted 被 accept = 漏(recall miss)。clean 真关系被 reject = FP(进人工池,可容忍)。**达标线:planted recall ≥ 0.9**(同 ②-B"包多可以包少不行"取向,FP 不设硬线)。

- [ ] **Step 1:** 写 `calibrate_3c_judge.py`(`--golden state/node3c/golden/golden_v1.jsonl --out state/node3c/reports_judge --judge-model deepseek-v4-flash`;断点续跑同 ②-B 校准器)。
- [ ] **Step 2:** 接线跑:`set -a; . ~/.config/policy-pipeline/models.env; set +a; OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=$DEEPSEEK_API_KEY python3 -m scripts._oneshot.calibrate_3c_judge ...`
- [ ] **Step 3:** 读分:**planted recall ≥ 0.9 → 达标**;否则改 `SEMANTIC_RELATION_JUDGE_SYSTEM`(针对漏的错型加规则)重跑,循环 ≤4 次;仍不达标 → 停、报告、交用户(可能换 judge 模型或缩关系范围)。
- [ ] **Step 4:** 提交校准证据:`git add scripts/_oneshot/calibrate_3c_judge.py && git add -f state/node3c/reports_judge && git commit -m "feat(③-C Task9): judge 校准(planted recall≥0.9 达标)"`

---

## Task 10: 真实 935 preview(只 preview)

- [ ] **Step 1:** 确认 ③-B 高精度候选最新产物路径(`state/analysis_layer/preview_*/high_precision_relation_candidates.jsonl`);若 stale,先重跑 ③-B preview。
- [ ] **Step 2:** 跑全量 preview(judge 已达标):
```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=$DEEPSEEK_API_KEY \
python3 -m scripts.analysis_semantic_relations.run preview \
  --vault "$HOME/Documents/Zayn Main/政策分析" \
  --state state/node3c/sem_preview_$(date +%Y%m%d) \
  --hpr state/analysis_layer/preview_<latest>/high_precision_relation_candidates.jsonl \
  --judge-model deepseek-v4-flash
```
  ⚠ 候选量可能上万 → judge 调用多;用 Task10 前先看 `semantic_relation_candidates.jsonl` 行数估成本,必要时分块(复用 `run935_driver.py` 的孤儿化+caffeinate 模式,按候选分块)。
- [ ] **Step 3:** 验收门自检(spec §10):无 vault/raw 写、无 apply、manual_review 不在 accepted、对称无重复、无未裁决方向矛盾、HTML 三类清楚。
- [ ] **Step 4:** 出中文报告 + 提交证据(`git add -f state/node3c/sem_preview_*`)。**到此为止——不 apply、不进 ④。** apply(写 vault relations)与 ④ 消费(含 Lever B)另行批准。

---

## Self-Review

**Spec coverage:** §4 关系分层→Task3;§5 四层机制→Task3(候选)/5(判定)/4(门)/8-9(人工池+校准);§6 数据契约→Task1/6;§7 普通模型约束→Task5 prompt;§10 验收门→Task6 summary.notes + Task10 Step3;§12 收敛→Task3(TOP_K/WINDOW);§13 golden+校准→Task7-9;§14 对称/方向→Task1(canonical)/3(去重)/4(方向矛盾)。**Lever B(§10.5)= 明确 out-of-scope(④ 实现)**,已在 Scope 标注。`conflicts_with` 不生成,已标注。

**Placeholder scan:** Task1-6 含完整 test+impl 代码;Task7-9 为 oneshot/模型工作流,给出脚本职责 + 镜像的现存模板(`sample_golden_2b.py`/`wf_gold_label.js`/`calibrate_judge_2b.py`)+ ③-C 特定 prompt/schema/达标线,非空占位。Task6 report.py 指明"镜像 ③-B report.py 结构 + 换字段"——模板是现存真实文件。

**Type consistency:** `SemanticCandidate.to_row()` 产 `from/to/rel/candidate_basis/evidence/symmetric/candidate_id` 字段,与 program_gate.REQUIRED、run_preview、judge_candidate 读的键一致;`generate_candidates` 返回 `SemanticCandidate` 列表,run 里 `.to_row()` 转 dict 后过门——一致。`judge_candidate` 入参为候选 dict(含 evidence),与 run 里传 `c`(已 to_row)一致。

**风险点(实施者注意):** ③-C 候选量可能很大(top-k=8 × 836 篇 × 4 关系 ≈ 上万),Task10 必须先估量再决定是否分块跑 judge,别盲目全量串行(同 ②-B 935 的教训)。
