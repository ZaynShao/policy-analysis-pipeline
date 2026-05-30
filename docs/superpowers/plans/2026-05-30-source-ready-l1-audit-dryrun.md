# L1 源到位 · Dry-run 审计引擎 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 pipeline 仓新建一个 dry-run 审计引擎，扫存量 vault L1（~999 政策），产出一份审计报告 + `proposed_changes.jsonl`，**零变更**地暴露：哪些是新闻稿、哪些 id-issuer 不一致、哪些重复、哪些残留 P_1900。

**Architecture:** 纯读取 + 纯函数为主。复用 `l1_collect/news_filter`（heuristic 预筛）与 `l1_collect/dedup`（三维归一化）。唯一新外部依赖是一个最小的、带日志的 LLM client（`scripts/common/llm.py`），仅用于对 heuristic-flagged 的候选逐条确认"政策 vs 新闻稿"。分类器对 LLM 调用做依赖注入（DI），单测用 fake，真跑用真 client。本计划**不做任何 apply / mutation**（归档移动、id 修正在 Phase 2 另一计划）。

**Tech Stack:** Python 3.9+，pytest，PyYAML，anthropic SDK（新增依赖，仅 client 用）。frontmatter 用 `re` + `yaml.safe_load`（沿用仓内约定，不引 python-frontmatter）。

**关键路径常量：** vault policies 目录 = `/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/`。

---

## File Structure（先锁边界）

| 文件 | 职责 | 依赖 |
|---|---|---|
| `scripts/l1_audit/__init__.py` | 包标记 | — |
| `scripts/l1_audit/models.py` | `PolicyRecord` / `Finding` 数据类（全模块共享）| stdlib |
| `scripts/l1_audit/corpus.py` | 读 vault → `list[PolicyRecord]`（frontmatter+body 解析）| yaml, models |
| `scripts/common/__init__.py` | 包标记 | — |
| `scripts/common/llm.py` | 最小 LLM client：`complete(system,user)->str`，temp=0，调用日志（LESSONS A5）| anthropic |
| `scripts/l1_audit/news_classifier.py` | heuristic 预筛(复用 news_filter) + LLM 逐条确认 → Findings | news_filter, models |
| `scripts/l1_audit/id_issuer_check.py` | issuer→short 表 + id 前缀一致性检查 → Findings | models |
| `scripts/l1_audit/dedup_group.py` | 复用 dedup 归一化，**分组**存量重复 → Findings | dedup, models |
| `scripts/l1_audit/scans.py` | 残留 P_1900 扫描 → Findings | models |
| `scripts/l1_audit/report.py` | 汇总 Findings → `audit_report.md` + `proposed_changes.jsonl` | models |
| `scripts/l1_audit/run_audit.py` | dry-run 编排 CLI（串起所有检查 → report）| 以上全部 |
| `tests/l1_audit/conftest.py` | 临时 vault fixture（含植入样本）| pytest |
| `tests/l1_audit/test_*.py` | 各模块单测 + 集成 | — |

**共享类型（Task 1 定义，后续任务引用，签名固定）：**

```python
# scripts/l1_audit/models.py
from dataclasses import dataclass, field

@dataclass
class PolicyRecord:
    pid: str                 # frontmatter id
    path: str                # 绝对路径
    title: str
    official_number: str
    date: str                # "YYYY-MM-DD" 或 ""
    issuer: list             # 统一为 list[str]（单值也包成 list）
    issuer_canonical: list   # 统一为 list[str]
    url: str
    body_head: str           # 正文前 2000 字符（喂 LLM 用）
    raw_fm: dict             # 原始 frontmatter dict

@dataclass
class Finding:
    check: str               # "news_release" | "id_issuer" | "dedup" | "p1900"
    pid: str
    detail: dict = field(default_factory=dict)
    proposed_action: str = ""   # 人类可读的提议（dry-run 只写不执行）
```

---

## Task 1: 共享类型 + corpus 加载器

**Files:**
- Create: `scripts/l1_audit/__init__.py`（空）
- Create: `scripts/l1_audit/models.py`
- Create: `scripts/l1_audit/corpus.py`
- Create: `tests/l1_audit/__init__.py`（空）
- Create: `tests/l1_audit/conftest.py`
- Test: `tests/l1_audit/test_corpus.py`

- [ ] **Step 1: 写 conftest fixture（临时 vault）**

```python
# tests/l1_audit/conftest.py
import textwrap
import pytest

def _policy_md(fm_yaml: str, body: str = "## 政策原文\n正文内容。") -> str:
    return f"---\n{fm_yaml.strip()}\n---\n\n{body}\n"

@pytest.fixture
def vault_policies(tmp_path):
    d = tmp_path / "0_raw" / "policies"
    d.mkdir(parents=True)
    (d / "good.md").write_text(_policy_md(textwrap.dedent("""
        id: P_2025_NDRC_357_a
        title: 关于加快推进虚拟电厂发展的指导意见
        official_number: 发改能源〔2025〕357号
        date: '2025-03-01'
        issuer: 国家发展和改革委员会
        issuer_canonical: [ndrc]
        provenance:
          url: https://www.ndrc.gov.cn/a/2025-03-01/x.html
        region:
          level: 国家
    """)), encoding="utf-8")
    return d
```

- [ ] **Step 2: 写 failing test**

```python
# tests/l1_audit/test_corpus.py
from scripts.l1_audit.corpus import load_policies

def test_load_parses_frontmatter_and_normalizes_issuer(vault_policies):
    recs = load_policies(str(vault_policies))
    assert len(recs) == 1
    r = recs[0]
    assert r.pid == "P_2025_NDRC_357_a"
    assert r.issuer == ["国家发展和改革委员会"]      # 单值包成 list
    assert r.issuer_canonical == ["ndrc"]
    assert r.url == "https://www.ndrc.gov.cn/a/2025-03-01/x.html"
    assert r.date == "2025-03-01"
    assert r.body_head.startswith("## 政策原文")
```

- [ ] **Step 3: 运行确认失败**

Run: `cd ~/dev/政策分析-pipeline && python -m pytest tests/l1_audit/test_corpus.py -v`
Expected: FAIL（ModuleNotFoundError: scripts.l1_audit.corpus）

- [ ] **Step 4: 写 models.py（即上方"共享类型"代码块全文）**

- [ ] **Step 5: 写 corpus.py 实现**

```python
# scripts/l1_audit/corpus.py
from __future__ import annotations
import re
from pathlib import Path
import yaml
from scripts.l1_audit.models import PolicyRecord

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)

def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]

def parse_policy_file(path: str) -> PolicyRecord | None:
    text = Path(path).read_text(encoding="utf-8")
    m = _FM_RE.search(text)
    if not m:
        return None
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2) or ""
    prov = fm.get("provenance") or {}
    return PolicyRecord(
        pid=fm.get("id") or "",
        path=str(path),
        title=fm.get("title") or "",
        official_number=fm.get("official_number") or "",
        date=str(fm.get("date") or ""),
        issuer=_as_list(fm.get("issuer")),
        issuer_canonical=_as_list(fm.get("issuer_canonical")),
        url=prov.get("url") or fm.get("source_url") or "",
        body_head=body[:2000],
        raw_fm=fm,
    )

def load_policies(policies_dir: str) -> list[PolicyRecord]:
    out = []
    for f in sorted(Path(policies_dir).glob("*.md")):
        rec = parse_policy_file(str(f))
        if rec is not None:
            out.append(rec)
    return out
```

- [ ] **Step 6: 运行确认通过**

Run: `python -m pytest tests/l1_audit/test_corpus.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/l1_audit/__init__.py scripts/l1_audit/models.py scripts/l1_audit/corpus.py tests/l1_audit/
git commit -m "feat(l1_audit): corpus loader + shared models"
```

---

## Task 2: 最小 LLM client（带调用日志）

**Files:**
- Create: `scripts/common/__init__.py`（空）
- Create: `scripts/common/llm.py`
- Test: `tests/common/test_llm.py`
- Modify: `pyproject.toml`（加 anthropic 依赖说明）

- [ ] **Step 1: 写 failing test（只测日志契约，不打真网络）**

```python
# tests/common/test_llm.py
import json
from scripts.common.llm import LLMClient

class _FakeMessages:
    def create(self, **kw):
        class R:  # 模拟 anthropic 响应
            content = [type("B", (), {"text": "POLICY"})()]
        return R()

class _FakeAnthropic:
    def __init__(self, **kw): self.messages = _FakeMessages()

def test_complete_returns_text_and_logs(tmp_path):
    log = tmp_path / "llm_calls.jsonl"
    c = LLMClient(client=_FakeAnthropic(), model="m-test", log_path=str(log))
    out = c.complete("sys", "user")
    assert out == "POLICY"
    line = json.loads(log.read_text().strip())
    assert line["model"] == "m-test"
    assert line["temperature"] == 0
    assert "prompt_sha" in line and "ts" in line
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/common/test_llm.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 llm.py 实现**

```python
# scripts/common/llm.py
"""最小 Claude client。temperature=0；每次调用写日志(LESSONS A5)。
真跑时从环境读 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL(中国代理)。"""
from __future__ import annotations
import os, json, hashlib, datetime
from pathlib import Path

DEFAULT_MODEL = "claude-opus-4-7"

class LLMClient:
    def __init__(self, client=None, model: str = DEFAULT_MODEL,
                 log_path: str = "state/source_ready/llm_calls.jsonl"):
        if client is None:
            import anthropic
            client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                base_url=os.environ.get("ANTHROPIC_BASE_URL") or None,
            )
        self._client = client
        self.model = model
        self.log_path = log_path

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        resp = self._client.messages.create(
            model=self.model, max_tokens=max_tokens, temperature=0,
            system=system, messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content)
        self._log(system, user, text)
        return text

    def _log(self, system: str, user: str, output: str) -> None:
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "model": self.model, "temperature": 0,
            "prompt_sha": hashlib.sha1((system + "\x00" + user).encode()).hexdigest()[:16],
            "output_chars": len(output),
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/common/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: 加依赖 + 安装**

`pyproject.toml` 在 `[project]` 段下新增：
```toml
dependencies = ["pyyaml", "anthropic>=0.40"]
```
Run: `pip install anthropic pyyaml`
Expected: 安装成功（真跑 client 时需要；单测用 fake 不依赖网络）

- [ ] **Step 6: Commit**

```bash
git add scripts/common/__init__.py scripts/common/llm.py tests/common/ pyproject.toml
git commit -m "feat(common): minimal logged Claude client (temp=0)"
```

---

## Task 3: 新闻稿分类器（heuristic 预筛 + LLM 确认，DI）

**Files:**
- Create: `scripts/l1_audit/news_classifier.py`
- Test: `tests/l1_audit/test_news_classifier.py`

- [ ] **Step 1: 写 failing test（LLM 用 fake 注入）**

```python
# tests/l1_audit/test_news_classifier.py
from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.news_classifier import classify_corpus

def _rec(pid, title, url, issuer):
    return PolicyRecord(pid=pid, path=f"/x/{pid}.md", title=title,
        official_number="", date="2025-01-01", issuer=[issuer] if issuer else [],
        issuer_canonical=[], url=url, body_head="正文", raw_fm={})

def test_obvious_policy_not_flagged_skips_llm():
    calls = []
    def fake_llm(system, user): calls.append(user); return "{}"
    recs = [_rec("P_2025_NDRC_1", "关于推进虚拟电厂的通知",
                 "https://www.ndrc.gov.cn/x.html", "国家发展和改革委员会")]
    findings = classify_corpus(recs, fake_llm)
    assert findings == []          # heuristic 通过 → 不进 LLM
    assert calls == []

def test_heuristic_flagged_then_llm_confirms_news():
    def fake_llm(system, user):
        return '{"label":"news_release","confidence":0.97,"evidence":"媒体转载"}'
    recs = [_rec("P_2025_X_2", "某新政解读_市县",
                 "https://www.sohu.com/a.html", "搜狐")]
    findings = classify_corpus(recs, fake_llm)
    assert len(findings) == 1
    f = findings[0]
    assert f.check == "news_release"
    assert f.detail["label"] == "news_release"
    assert f.detail["confidence"] == 0.97
    assert "_archive" in f.proposed_action
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_audit/test_news_classifier.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 news_classifier.py 实现**

```python
# scripts/l1_audit/news_classifier.py
"""政策 vs 新闻稿:heuristic 预筛(复用 news_filter) → LLM 逐条确认 flagged。"""
from __future__ import annotations
import json
from typing import Callable
from scripts.l1_collect.news_filter import is_news_or_press
from scripts.l1_audit.models import PolicyRecord, Finding

LLMFn = Callable[[str, str], str]   # (system, user) -> raw text

_SYSTEM = (
    "你是政策文档分类器。判断给定文档是『正式政策公文』还是"
    "『新闻稿/报道/索引页/纯转载』。只输出 JSON,无解释。"
    'schema: {"label": "policy|news_release|index_page|reprint_only",'
    ' "confidence": 0-1, "evidence": "<=30字依据"}'
)

def _heuristic_flagged(rec: PolicyRecord) -> bool:
    issuer = rec.issuer[0] if rec.issuer else None
    return is_news_or_press(rec.url, rec.title, issuer).is_filtered

def classify_one(rec: PolicyRecord, llm_fn: LLMFn) -> Finding | None:
    if not _heuristic_flagged(rec):
        return None                      # 明显政策,跳过 LLM
    user = f"标题:{rec.title}\nURL:{rec.url}\n正文开头:{rec.body_head[:800]}"
    try:
        data = json.loads(llm_fn(_SYSTEM, user))
    except (json.JSONDecodeError, TypeError):
        return Finding(check="news_release", pid=rec.pid,
                       detail={"label": "unresolved"},
                       proposed_action="LLM 解析失败 → 人工清单")
    if data.get("label", "policy") == "policy":
        return None                      # LLM 平反:确是政策
    return Finding(check="news_release", pid=rec.pid, detail=data,
                   proposed_action=f"迁 _archive/policies/news_release/ ({data.get('label')})")

def classify_corpus(records: list[PolicyRecord], llm_fn: LLMFn) -> list[Finding]:
    out = []
    for r in records:
        f = classify_one(r, llm_fn)
        if f is not None:
            out.append(f)
    return out
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_audit/test_news_classifier.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_audit/news_classifier.py tests/l1_audit/test_news_classifier.py
git commit -m "feat(l1_audit): news-release classifier (heuristic + LLM confirm)"
```

---

## Task 4: id-issuer 一致性检查

**Files:**
- Create: `scripts/l1_audit/id_issuer_check.py`
- Test: `tests/l1_audit/test_id_issuer_check.py`

- [ ] **Step 1: 写 failing test**

```python
# tests/l1_audit/test_id_issuer_check.py
from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.id_issuer_check import parse_issuer_short, check_corpus

def _rec(pid, issuer, canon=None):
    return PolicyRecord(pid=pid, path="/x.md", title="t", official_number="",
        date="2024-01-01", issuer=[issuer], issuer_canonical=canon or [],
        url="", body_head="", raw_fm={})

def test_parse_issuer_short_handles_multiseg():
    assert parse_issuer_short("P_2024_NDRC_718") == "NDRC"
    assert parse_issuer_short("P_2025_BJ_DRC_8") == "BJ_DRC"

def test_flags_mismatch_only():
    recs = [
        _rec("P_2024_NDRC_718", "国家发展和改革委员会", ["ndrc"]),   # 一致
        _rec("P_2024_GO_7", "广州市商务局", []),                     # 错:GO=国务院
    ]
    findings = check_corpus(recs)
    assert len(findings) == 1
    assert findings[0].pid == "P_2024_GO_7"
    assert findings[0].check == "id_issuer"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_audit/test_id_issuer_check.py -v`
Expected: FAIL

- [ ] **Step 3: 写 id_issuer_check.py 实现**

```python
# scripts/l1_audit/id_issuer_check.py
"""id 前缀 issuer_short 与 issuer 字段一致性(dry-run flag,不修)。
表 seed 自 SCHEMA §2;不在表内的 short(市级 XX_*)跳过,不误报。"""
from __future__ import annotations
from scripts.l1_audit.models import PolicyRecord, Finding

# issuer_short -> 该机构名里应出现的关键字
SHORT_TO_ISSUER_KW = {
    "NDRC": "发展和改革", "NEA": "能源局", "MIIT": "工业和信息化",
    "MOFCOM": "商务部", "MOHURD": "住房和城乡建设", "MEE": "生态环境",
    "MOF": "财政部", "SC": "国务院", "GO": "国务院办公厅", "PBOC": "中国人民银行",
}

def parse_issuer_short(pid: str) -> str:
    parts = pid.split("_")
    if len(parts) < 4:           # P_year_short_num
        return ""
    return "_".join(parts[2:-1])

def check_one(rec: PolicyRecord) -> Finding | None:
    short = parse_issuer_short(rec.pid)
    kw = SHORT_TO_ISSUER_KW.get(short)
    if kw is None:               # 市级/未知 short,本检查不管
        return None
    issuer_text = " ".join(rec.issuer)
    if kw in issuer_text:
        return None              # 一致
    return Finding(check="id_issuer", pid=rec.pid,
                   detail={"id_short": short, "issuer": rec.issuer, "expected_kw": kw},
                   proposed_action=f"id 前缀 {short} 与 issuer({issuer_text}) 不符 → 人工/重算复核")

def check_corpus(records: list[PolicyRecord]) -> list[Finding]:
    return [f for r in records if (f := check_one(r)) is not None]
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_audit/test_id_issuer_check.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_audit/id_issuer_check.py tests/l1_audit/test_id_issuer_check.py
git commit -m "feat(l1_audit): id-issuer consistency check"
```

---

## Task 5: 存量重复分组

**Files:**
- Create: `scripts/l1_audit/dedup_group.py`
- Test: `tests/l1_audit/test_dedup_group.py`

- [ ] **Step 1: 写 failing test**

```python
# tests/l1_audit/test_dedup_group.py
from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.dedup_group import group_duplicates

def _rec(pid, url, offnum, title, date):
    return PolicyRecord(pid=pid, path=f"/{pid}.md", title=title, official_number=offnum,
        date=date, issuer=[], issuer_canonical=[], url=url, body_head="", raw_fm={})

def test_groups_by_any_dimension_and_keeps_earliest():
    recs = [
        _rec("P_A", "https://x.gov.cn/a/", "发改〔2024〕1号", "标题甲", "2024-01-01"),
        _rec("P_B", "https://x.gov.cn/a",  "发改〔2024〕1号", "标题甲(转)", "2024-02-01"),  # 同URL/同文号
        _rec("P_C", "https://y.gov.cn/z",  "", "完全不同的政策", "2024-03-01"),            # 独立
    ]
    findings = group_duplicates(recs)
    assert len(findings) == 1                 # 一个重复组
    f = findings[0]
    assert f.detail["keep"] == "P_A"          # 最早
    assert set(f.detail["dups"]) == {"P_B"}
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_audit/test_dedup_group.py -v`
Expected: FAIL

- [ ] **Step 3: 写 dedup_group.py 实现**

```python
# scripts/l1_audit/dedup_group.py
"""存量重复分组:三维(URL/文号/标题)任一命中即同组(复用 dedup 归一化)。
每组留 date 最早者,其余提议迁 _duplicates。"""
from __future__ import annotations
from scripts.l1_collect.dedup import normalize_url, normalize_official_number, normalize_title
from scripts.l1_audit.models import PolicyRecord, Finding

class _UF:  # union-find
    def __init__(self): self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        self.p[self.find(b)] = self.find(a)

def group_duplicates(records: list[PolicyRecord]) -> list[Finding]:
    uf = _UF()
    for dim, norm, attr in (
        ("url", normalize_url, "url"),
        ("off", normalize_official_number, "official_number"),
        ("title", normalize_title, "title"),
    ):
        seen = {}
        for r in records:
            key = norm(getattr(r, attr))
            if not key:
                continue
            if key in seen:
                uf.union(seen[key].pid, r.pid)
            else:
                seen[key] = r
    by_pid = {r.pid: r for r in records}
    groups: dict[str, list[str]] = {}
    for r in records:
        groups.setdefault(uf.find(r.pid), []).append(r.pid)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda p: (by_pid[p].date or "9999", p))  # 最早在前
        keep, dups = members[0], members[1:]
        out.append(Finding(check="dedup", pid=keep,
                           detail={"keep": keep, "dups": dups},
                           proposed_action=f"留 {keep};{dups} 迁 _duplicates/"))
    return out
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_audit/test_dedup_group.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_audit/dedup_group.py tests/l1_audit/test_dedup_group.py
git commit -m "feat(l1_audit): existing-corpus duplicate grouping (union-find over 3 dims)"
```

---

## Task 6: 残留 P_1900 扫描

**Files:**
- Create: `scripts/l1_audit/scans.py`
- Test: `tests/l1_audit/test_scans.py`

- [ ] **Step 1: 写 failing test**

```python
# tests/l1_audit/test_scans.py
from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.scans import scan_p1900

def _rec(pid): return PolicyRecord(pid=pid, path=f"/{pid}.md", title="t",
    official_number="", date="", issuer=[], issuer_canonical=[], url="", body_head="", raw_fm={})

def test_flags_p1900_only():
    recs = [_rec("P_1900_SX_caf8e7eb"), _rec("P_2025_NDRC_1")]
    findings = scan_p1900(recs)
    assert len(findings) == 1
    assert findings[0].pid == "P_1900_SX_caf8e7eb"
    assert findings[0].check == "p1900"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_audit/test_scans.py -v`
Expected: FAIL

- [ ] **Step 3: 写 scans.py 实现**

```python
# scripts/l1_audit/scans.py
"""残留 P_1900_*(date 真空占位)扫描。"""
from __future__ import annotations
from scripts.l1_audit.models import PolicyRecord, Finding

def scan_p1900(records: list[PolicyRecord]) -> list[Finding]:
    return [Finding(check="p1900", pid=r.pid, detail={},
                    proposed_action="date 真空 → backlog 人工补 date 重算 id")
            for r in records if r.pid.startswith("P_1900_")]
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_audit/test_scans.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_audit/scans.py tests/l1_audit/test_scans.py
git commit -m "feat(l1_audit): residual P_1900 scan"
```

---

## Task 7: 报告 + proposed_changes 落盘

**Files:**
- Create: `scripts/l1_audit/report.py`
- Test: `tests/l1_audit/test_report.py`

- [ ] **Step 1: 写 failing test**

```python
# tests/l1_audit/test_report.py
import json
from scripts.l1_audit.models import Finding
from scripts.l1_audit.report import write_outputs

def test_write_outputs_creates_report_and_jsonl(tmp_path):
    findings = [
        Finding(check="news_release", pid="P_X", detail={"label": "news_release"}, proposed_action="迁档"),
        Finding(check="dedup", pid="P_A", detail={"keep": "P_A", "dups": ["P_B"]}, proposed_action="去重"),
    ]
    out_dir = tmp_path / "state" / "source_ready"
    write_outputs(findings, total_policies=999, out_dir=str(out_dir))
    report = (out_dir / "audit_report.md").read_text(encoding="utf-8")
    assert "999" in report and "news_release: 1" in report and "dedup: 1" in report
    lines = (out_dir / "proposed_changes.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["pid"] == "P_X"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_audit/test_report.py -v`
Expected: FAIL

- [ ] **Step 3: 写 report.py 实现**

```python
# scripts/l1_audit/report.py
"""dry-run 产出:audit_report.md(人读) + proposed_changes.jsonl(机器读)。"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from dataclasses import asdict
from scripts.l1_audit.models import Finding

def write_outputs(findings: list[Finding], total_policies: int, out_dir: str) -> None:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    counts = Counter(f.check for f in findings)
    # jsonl
    with open(Path(out_dir) / "proposed_changes.jsonl", "w", encoding="utf-8") as f:
        for fd in findings:
            f.write(json.dumps(asdict(fd), ensure_ascii=False) + "\n")
    # report
    lines = ["# L1 Dry-run 审计报告", "",
             f"- 扫描政策总数: {total_policies}",
             f"- flagged 总数: {len(findings)}", "", "## 按类计数"]
    for check in ("news_release", "id_issuer", "dedup", "p1900"):
        lines.append(f"- {check}: {counts.get(check, 0)}")
    lines += ["", "## 判断型类(需抽样校 ≥95% 才自动应用)",
              "- news_release / dedup → 见 proposed_changes.jsonl,Phase 2 抽样后应用",
              "", "## 确定性类", "- id_issuer / p1900 → 人工/规则复核"]
    (Path(out_dir) / "audit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_audit/test_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_audit/report.py tests/l1_audit/test_report.py
git commit -m "feat(l1_audit): audit report + proposed_changes writer"
```

---

## Task 8: dry-run 编排 CLI + 集成测试

**Files:**
- Create: `scripts/l1_audit/run_audit.py`
- Test: `tests/l1_audit/test_run_audit_integration.py`

- [ ] **Step 1: 写 failing 集成 test（端到端 dry-run,LLM 用 fake）**

```python
# tests/l1_audit/test_run_audit_integration.py
import json, textwrap
from scripts.l1_audit.run_audit import run_dry_run

def _write(d, name, fm, body="## 政策原文\n正文。"):
    (d / name).write_text(f"---\n{textwrap.dedent(fm).strip()}\n---\n\n{body}\n", encoding="utf-8")

def test_end_to_end_dry_run(tmp_path):
    pol = tmp_path / "0_raw" / "policies"; pol.mkdir(parents=True)
    _write(pol, "good.md", """
        id: P_2025_NDRC_357_a
        title: 关于加快推进虚拟电厂发展的指导意见
        issuer: 国家发展和改革委员会
        provenance: {url: 'https://www.ndrc.gov.cn/a/x.html'}
        date: '2025-03-01'
    """)
    _write(pol, "news.md", """
        id: P_2025_X_news
        title: 某政策解读_市县
        issuer: 搜狐
        provenance: {url: 'https://www.sohu.com/a.html'}
        date: '2025-04-01'
    """)
    out_dir = tmp_path / "state" / "source_ready"
    def fake_llm(system, user):
        return '{"label":"news_release","confidence":0.97,"evidence":"媒体"}'
    run_dry_run(policies_dir=str(pol), out_dir=str(out_dir), llm_fn=fake_llm)
    lines = (out_dir / "proposed_changes.jsonl").read_text(encoding="utf-8").strip().splitlines()
    pids = {json.loads(l)["pid"] for l in lines}
    assert "P_2025_X_news" in pids        # 新闻稿被 flag
    assert "P_2025_NDRC_357_a" not in pids # 真政策不被 flag
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/l1_audit/test_run_audit_integration.py -v`
Expected: FAIL

- [ ] **Step 3: 写 run_audit.py 实现**

```python
# scripts/l1_audit/run_audit.py
"""L1 dry-run 审计编排。零变更:只读 vault → 跑 4 类检查 → 写报告。
真跑: python -m scripts.l1_audit.run_audit --policies-dir <vault>/0_raw/policies"""
from __future__ import annotations
import argparse
from typing import Callable, Optional
from scripts.l1_audit.corpus import load_policies
from scripts.l1_audit.news_classifier import classify_corpus
from scripts.l1_audit.id_issuer_check import check_corpus
from scripts.l1_audit.dedup_group import group_duplicates
from scripts.l1_audit.scans import scan_p1900
from scripts.l1_audit.report import write_outputs

def run_dry_run(policies_dir: str, out_dir: str,
                llm_fn: Optional[Callable[[str, str], str]] = None) -> None:
    if llm_fn is None:
        from scripts.common.llm import LLMClient
        llm_fn = LLMClient().complete
    recs = load_policies(policies_dir)
    findings = []
    findings += classify_corpus(recs, llm_fn)
    findings += check_corpus(recs)
    findings += group_duplicates(recs)
    findings += scan_p1900(recs)
    write_outputs(findings, total_policies=len(recs), out_dir=out_dir)
    print(f"[dry-run] policies={len(recs)} findings={len(findings)} → {out_dir}")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies-dir", required=True)
    ap.add_argument("--out-dir", default="state/source_ready")
    run_dry_run(ap.parse_args().policies_dir, ap.parse_args().out_dir)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/l1_audit/test_run_audit_integration.py -v`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `python -m pytest tests/l1_audit tests/common -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/l1_audit/run_audit.py tests/l1_audit/test_run_audit_integration.py
git commit -m "feat(l1_audit): dry-run orchestrator CLI + e2e integration test"
```

---

## 真跑 dry-run（实现完成后，人工执行一次，非自动步骤）

```bash
cd ~/dev/政策分析-pipeline
export ANTHROPIC_API_KEY=...        # 中国代理另设 ANTHROPIC_BASE_URL
python -m scripts.l1_audit.run_audit \
  --policies-dir "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies"
# 看 state/source_ready/audit_report.md 与 proposed_changes.jsonl
```
**这一步只读不改**。看完报告、确认 flagged 量级合理后，才进 Phase 2（抽样校 ≥95% → 应用）——Phase 2 是另一份计划。

---

## Self-Review

**Spec 覆盖：** spec §3.2 四类检查 → Task 3(news)/4(id_issuer)/5(dedup)/6(p1900) 全覆盖；§3.3 heuristic+LLM → Task 3；§3.1 dry-run 零变更 → Task 8 编排只读;report → Task 7。**spec §3.4(抽样)/§3.5(应用)/§3.6(checkpoint) 属 Phase 2，本计划显式不含**（已在 Goal/真跑段标注）。子项 b(词表校)/c(框架结构化)未含 → 各自独立计划。

**Placeholder 扫描：** 无 TBD/TODO；每个 code step 有完整代码；命令含预期输出。

**类型一致性：** `PolicyRecord`/`Finding` 字段在 models.py 定义，各 Task 引用一致（`raw_fm`、`body_head`、`issuer: list`）；`LLMFn = Callable[[str,str],str]` 在 Task 2/3/8 签名一致；`classify_corpus(records, llm_fn)` / `check_corpus(records)` / `group_duplicates(records)` / `scan_p1900(records)` / `write_outputs(findings, total_policies, out_dir)` 在 Task 8 编排里调用签名一致。

**已知边界（非阻塞）：** id 解析 `parse_issuer_short` 对碰撞后缀(`_a`/`_b`)会把 short 多切一段——dry-run 仅 flag 供人工复核，可接受；Phase 2 若要自动重算需收紧。
