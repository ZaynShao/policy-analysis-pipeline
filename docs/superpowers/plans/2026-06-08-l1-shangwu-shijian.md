# L1 采集扩张:商务厅 + 市监局 + gate commentary — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 L1 采集扩到商务厅(加油线)+ 市监局(企业背景维度),并让 gate 学会 commentary 标签把解读/问答路由到 commentaries/,含一次带审核的存量回扫。

**Architecture:** 全部就地扩展 `scripts/l1_collect/`(5 组件)。发现/扫描解耦:域名无关发现只在一次性 expand 跑;循环 `run_incremental` 只扫验证渠道。commentary 路由 + 存量回扫共用一个泛化的 `route_files` 转换。

**Tech Stack:** Python 3.9 / pytest / 现有 l1_collect 模块(channel_discovery / step2_scan / policy_gate / run_incremental / connectivity_probe)/ Tavily + firecrawl(SaaS)/ deepseek-flash judge。

设计 spec:`docs/superpowers/specs/2026-06-08-l1-shangwu-shijian-design.md`。

**纪律**:续 `feat/l1-capture-repair` 同 worktree;models.env 凭据勿提交;raw 写走 §C;`git -C vault status -z` 取 UTF-8 路径;后台长抓孤儿化 `nohup caffeinate -i <cmd> >log 2>&1 & disown`。测试从 worktree 根跑:`python3 -m pytest tests/l1_collect/ -q`。

---

## 文件结构

| 文件 | 改动 | 职责 |
|------|------|------|
| `scripts/l1_collect/channel_discovery.py` | Modify | +`commerce_market_targets` +`discover_one` 域名无关支路 +`_institution_match` +`_is_gov_host` |
| `scripts/l1_collect/step2_scan.py` | Modify | KEYWORDS 加两域 |
| `scripts/l1_collect/policy_gate.py` | Modify | +COMMENTARY_MARKERS,_heuristic/gate_one commentary 标签 + LLM schema |
| `scripts/l1_collect/run_incremental.py` | Modify | `_gate_extracted_dir` 3-way + `ingest_commentary` + `_select_channels` channel_type 过滤 |
| `scripts/_oneshot/route_interpretations.py` | Modify | 抽 `route_files(paths, dry)` 共用转换(tracked git rm / untracked unlink) |
| `scripts/_oneshot/sweep_existing_commentary.py` | Create | 扫全量 policies/ marker → DRY → apply via route_files |
| `scripts/_oneshot/audit_coverage_raw.py` | Modify | THEMES 加「平台监管」列 |
| `scripts/_oneshot/expand_channels_l1.py` | Modify | 加 commerce_market 发现模式 |
| `scripts/_oneshot/build_l1_golden.py` | Modify | golden 加 commentary 类(18 篇) |
| `scripts/_oneshot/calibrate_l1_gate.py` | Modify | 加 commentary-recall 断言 |
| `tests/l1_collect/test_channel_discovery.py` | Modify | commerce_market_targets / 域名无关 discover / institution_match |
| `tests/l1_collect/test_step2_scan.py` | Modify | 新关键词过滤 |
| `tests/l1_collect/test_policy_gate.py` | Modify | commentary 标签 |
| `tests/l1_collect/test_run_incremental.py` | Modify | 3-way gate / channel_type 过滤 |
| `tests/l1_collect/test_route_files.py` | Create | route_files 转换 |

---

## Task 1: `commerce_market_targets()` 目标生成

**Files:**
- Modify: `scripts/l1_collect/channel_discovery.py`
- Test: `tests/l1_collect/test_channel_discovery.py`

- [ ] **Step 1: 写失败测试**

加到 `tests/l1_collect/test_channel_discovery.py`:
```python
def test_commerce_market_targets_shape():
    from scripts.l1_collect.channel_discovery import commerce_market_targets
    targets = commerce_market_targets()
    by_type = {}
    for t in targets:
        by_type.setdefault(t["channel_type"], []).append(t)
    # 商务: 31 省 + 10 重点市 ; 市监: 31 省
    assert len(by_type["商务"]) == 31 + 10
    assert len(by_type["市监"]) == 31
    # 直辖市商务用"商务局"显示名,省用"商务厅"
    names = {t["city"] for t in by_type["商务"]}
    assert "江苏省商务厅" in names
    assert "北京市商务局" in names
    assert "佛山市商务局" in names          # 重点市(加油线)
    # 市监显示名
    assert "江苏省市场监督管理局" in {t["city"] for t in by_type["市监"]}
    # 省级目标 root_domain 默认 None(待发现);市监全 None
    assert all(t["root_domain"] is None for t in by_type["市监"])

def test_commerce_warmstart_from_registry(tmp_path):
    """registry 已有的商务域名 → root_domain 预填(暖启动)。"""
    from scripts.l1_collect.channel_discovery import commerce_market_targets
    reg = tmp_path / "reg.yaml"
    reg.write_text(
        "- domain: swt.fujian.gov.cn\n  issuer_canonical: 福建省商务厅\n",
        encoding="utf-8")
    targets = commerce_market_targets(registry_path=reg)
    fj = [t for t in targets if t["city"] == "福建省商务厅"][0]
    assert fj["root_domain"] == "swt.fujian.gov.cn"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l1_collect/test_channel_discovery.py::test_commerce_market_targets_shape -v`
Expected: FAIL — `ImportError: cannot import name 'commerce_market_targets'`

- [ ] **Step 3: 实现**

在 `scripts/l1_collect/channel_discovery.py` 末尾加(`_PROV_CODE` 已存在,含 31 省;`MUNICIPALITIES` 从 city_priority 拿):
```python
from .city_priority import MUNICIPALITIES, BUSINESS_RULES

def _commerce_name(prov: str) -> str:
    return f"{prov}商务局" if prov in MUNICIPALITIES else f"{prov}商务厅"

def _warmstart_domains(registry_path) -> dict:
    """registry 里 issuer 含'商务' → {显示名: domain},用于暖启动。"""
    if registry_path is None or not Path(registry_path).exists():
        return {}
    raw = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or []
    out = {}
    for e in raw:
        iss = e.get("issuer_canonical") or ""
        dom = e.get("domain") or ""
        if "商务" in iss and dom:
            out[iss] = dom
    return out

def commerce_market_targets(registry_path: Optional[Path] = None) -> list:
    """商务厅(31省+加油线重点市)+ 市监局(31省)目标。root_domain 多为 None(待发现)。"""
    warm = _warmstart_domains(registry_path)
    oil_cities = sorted(BUSINESS_RULES["加油"][0]["cities"])  # 10 重点市
    out = []
    for prov, code in _PROV_CODE.items():
        cname = _commerce_name(prov)
        out.append({"city": cname, "province": prov, "level": "省",
                    "city_code": f"{code}0000", "channel_type": "商务",
                    "root_domain": warm.get(cname)})
        out.append({"city": f"{prov}市场监督管理局", "province": prov, "level": "省",
                    "city_code": f"{code}0000", "channel_type": "市监",
                    "root_domain": warm.get(f"{prov}市场监督管理局")})
    # 商务重点市(加油线)
    _CITY_CODE = {  # 加油线 10 市国标码(前缀省+市)
        "东莞市": "441900", "佛山市": "440600", "嘉兴市": "330400", "温州市": "330300",
        "泉州市": "350500", "南通市": "320600", "烟台市": "370600", "潍坊市": "370700",
        "常州市": "320400", "惠州市": "441300",
    }
    for city in oil_cities:
        out.append({"city": f"{city}商务局", "province": city, "level": "市",
                    "city_code": _CITY_CODE.get(city, ""), "channel_type": "商务",
                    "root_domain": warm.get(f"{city}商务局")})
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l1_collect/test_channel_discovery.py::test_commerce_market_targets_shape tests/l1_collect/test_channel_discovery.py::test_commerce_warmstart_from_registry -v`
Expected: PASS(2 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/channel_discovery.py tests/l1_collect/test_channel_discovery.py
git commit -m "feat(l1): commerce_market_targets 商务厅+市监局目标生成(暖启动)"
```

---

## Task 2: `discover_one` 域名无关支路 + `_institution_match`

**Files:**
- Modify: `scripts/l1_collect/channel_discovery.py`
- Test: `tests/l1_collect/test_channel_discovery.py`

- [ ] **Step 1: 写失败测试**

```python
def test_institution_match_by_domain():
    from scripts.l1_collect.channel_discovery import _institution_match
    assert _institution_match("swt.jiangsu.gov.cn", "商务") is True
    assert _institution_match("scjgj.beijing.gov.cn", "市监") is True
    assert _institution_match("amr.gd.gov.cn", "市监") is True
    assert _institution_match("fgw.sc.gov.cn", "商务") is False   # 发改委域名→不匹配商务
    assert _institution_match("nea.gov.cn", "市监") is False

def test_discover_domain_agnostic_derives_domain(monkeypatch):
    """域名未知:Tavily 返 gov+非gov → gov 过滤 → LLM 选 → 反推域名 → 机构核验 → 验证。"""
    from scripts.l1_collect import channel_discovery as cd
    from scripts.l1_collect.connectivity_probe import ProbeResult
    monkeypatch.setattr(cd, "_tavily_search",
                        lambda q: ["https://news.sina.com.cn/x",
                                   "https://swt.jiangsu.gov.cn/col/tzgg/"])
    monkeypatch.setattr(cd, "_llm_pick",
                        lambda name, urls: "https://swt.jiangsu.gov.cn/col/tzgg/")
    monkeypatch.setattr(cd, "probe_url",
                        lambda u, **k: ProbeResult(url=u, http_status=200,
                                                   page_has_list_pattern=True, verdict="ok"))
    ch = cd.discover_one({"city": "江苏省商务厅", "province": "江苏省", "level": "省",
                          "city_code": "320000", "channel_type": "商务",
                          "root_domain": None})
    assert ch.root_domain == "swt.jiangsu.gov.cn"   # 反推
    assert ch.status.value == "验证"

def test_discover_domain_agnostic_demotes_when_institution_mismatch(monkeypatch):
    """选中的是 gov 列表页但域名不像商务(发改委)→ 核验门降候选。"""
    from scripts.l1_collect import channel_discovery as cd
    from scripts.l1_collect.connectivity_probe import ProbeResult
    monkeypatch.setattr(cd, "_tavily_search",
                        lambda q: ["https://fgw.sc.gov.cn/zcfb/"])
    monkeypatch.setattr(cd, "_llm_pick", lambda name, urls: "https://fgw.sc.gov.cn/zcfb/")
    monkeypatch.setattr(cd, "probe_url",
                        lambda u, **k: ProbeResult(url=u, http_status=200,
                                                   page_has_list_pattern=True, verdict="ok"))
    ch = cd.discover_one({"city": "四川省商务厅", "province": "四川省", "level": "省",
                          "city_code": "510000", "channel_type": "商务",
                          "root_domain": None})
    assert ch.status.value == "候选"   # 域名核验没过 → 不验证
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l1_collect/test_channel_discovery.py::test_discover_domain_agnostic_derives_domain -v`
Expected: FAIL — `_institution_match` not defined / status 非"验证"

- [ ] **Step 3: 实现**

在 `channel_discovery.py` 顶部 import 加 `from .news_filter import GOV_DOMAIN_SUFFIXES`。加两个函数 + 改 `discover_one`:
```python
_INST_DOMAIN_MARKERS = {
    "商务": ("swt", "commerce", "mofcom", "sw."),
    "市监": ("scjg", "scjgj", "amr", "samr", "scjgdj"),
}

def _is_gov_host(url: str) -> bool:
    return any(_host(url).endswith(s) for s in GOV_DOMAIN_SUFFIXES)

def _institution_match(domain: str, channel_type: str) -> bool:
    """域名标记核验(防域名无关发现串味)。已知域名类型(发改委等)不在此路径。"""
    markers = _INST_DOMAIN_MARKERS.get(channel_type)
    if markers is None:           # 非商务/市监(已知域名路径)→ 不做此核验
        return True
    h = (domain or "").lower()
    return any(m in h for m in markers)
```

改 `discover_one`(替换 `on_domain` 计算 + status 判定):
```python
def discover_one(target: dict) -> Optional[Channel]:
    query = f"{target['city']} 政策文件 通知公告 列表"
    candidates = _tavily_search(query)
    known = target.get("root_domain")
    if known:
        on_domain = [u for u in candidates if _same_domain(u, known)]
    else:
        on_domain = [u for u in candidates if _is_gov_host(u)]   # 域名未知→gov 过滤
    picked = _llm_pick(target["city"], on_domain)
    ordered = ([picked] if picked else []) + [u for u in on_domain if u != picked]
    list_url, pr = _first_verified(ordered)
    if list_url is None:
        list_url = f"https://{known}/" if known else (
            f"https://{_host(picked)}/" if picked else "")
        pr = probe_url(list_url) if list_url else None
    resolved = known or (_host(list_url) if list_url else "")
    inst_ok = _institution_match(resolved, target["channel_type"])
    verdict_ok = bool(pr) and pr.verdict == "ok"
    status = ChannelStatus.验证 if (verdict_ok and inst_ok) else ChannelStatus.候选
    return Channel(
        city=target["city"], province=target["province"], level=target["level"],
        city_code=target["city_code"], channel_type=target["channel_type"],
        root_domain=resolved, list_url=list_url, source="discovery", status=status,
        last_probed_at=(pr.probed_at if pr else None),
        probe_result=(pr.verdict if pr else None),
    )
```

- [ ] **Step 4: 跑测试确认通过(含旧测试不回归)**

Run: `python3 -m pytest tests/l1_collect/test_channel_discovery.py -v`
Expected: PASS(含旧 `test_discover_builds_verified_channel` 等全绿)

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/channel_discovery.py tests/l1_collect/test_channel_discovery.py
git commit -m "feat(l1): discover_one 域名无关支路+机构名核验门(防串味)"
```

---

## Task 3: 关键词域扩展

**Files:**
- Modify: `scripts/l1_collect/step2_scan.py:27` (KEYWORDS)
- Test: `tests/l1_collect/test_step2_scan.py`

- [ ] **Step 1: 写失败测试**

加到 `tests/l1_collect/test_step2_scan.py`:
```python
def test_keywords_cover_oil_retail_and_market_reg():
    from scripts.l1_collect.step2_scan import KEYWORDS
    for kw in ("加油站", "成品油零售", "平台经济", "反垄断", "市场监管", "网络交易"):
        assert kw in KEYWORDS, f"缺关键词 {kw}"

def test_title_with_new_keyword_passes_filter():
    from scripts.l1_collect.step2_scan import KEYWORDS
    titles = ["浙江省成品油零售经营管理实施细则", "关于平台经济反垄断的指导意见"]
    for t in titles:
        assert any(kw in t for kw in KEYWORDS)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l1_collect/test_step2_scan.py::test_keywords_cover_oil_retail_and_market_reg -v`
Expected: FAIL — `缺关键词 加油站`

- [ ] **Step 3: 实现**

`scripts/l1_collect/step2_scan.py` 把 KEYWORDS 末尾(右括号前)加两行:
```python
    # 加油线(商务厅):成品油零售/加油站
    "加油站", "成品油零售", "油品经营", "加油", "燃油",
    # 市场监管/平台(市监局·企业背景):
    "平台经济", "反垄断", "反不正当竞争", "市场监管", "网络交易",
    "互联网平台", "经营者集中", "公平竞争审查", "价格监管",
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l1_collect/test_step2_scan.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/step2_scan.py tests/l1_collect/test_step2_scan.py
git commit -m "feat(l1): scan 关键词加 加油线+市场监管/平台 两域"
```

---

## Task 4: gate commentary 标签

**Files:**
- Modify: `scripts/l1_collect/policy_gate.py`
- Test: `tests/l1_collect/test_policy_gate.py`

- [ ] **Step 1: 写失败测试**

```python
def test_heuristic_commentary_before_gov_fastpass():
    """《X办法》政策解读:含'办法'政策信号+gov域,但应先判 commentary(堵旧洞)。"""
    from scripts.l1_collect.policy_gate import _heuristic
    v = _heuristic("https://fgw.sc.gov.cn/zcjd/x.html",
                   "《四川省绿电直连实施细则》政策解读", "")
    assert v == "commentary"

def test_gate_one_commentary_action():
    from scripts.l1_collect.policy_gate import gate_one
    gr = gate_one("p1", "https://x.gov.cn/zcjd/a.html",
                  "《某办法》答记者问", "记者问……", llm_fn=None)
    assert gr.label == "commentary"
    assert gr.action == "commentary"

def test_gate_one_llm_commentary_label_maps_to_action():
    import json
    from scripts.l1_collect.policy_gate import gate_one
    def fake(system, user):
        return json.dumps({"label": "commentary", "confidence": 0.9, "evidence": "解读口径"})
    gr = gate_one("p2", "https://x.gov.cn/a.html", "某通知", "本文解读……", llm_fn=fake)
    assert gr.action == "commentary"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l1_collect/test_policy_gate.py::test_heuristic_commentary_before_gov_fastpass -v`
Expected: FAIL — `assert 'policy' == 'commentary'`

- [ ] **Step 3: 实现**

`policy_gate.py`:加常量(POLICY_TITLE_SIGNALS 附近):
```python
COMMENTARY_MARKERS = ("政策解读", "解读材料", "文字解读", "答记者问",
                      "一图读懂", "图解", "图读", "问答")
```
`_heuristic` 在 `_blacklisted` 之后、gov 快通之前插:
```python
    if _blacklisted(url):
        return "non_policy"
    if any(m in title for m in COMMENTARY_MARKERS):   # 新:gov 快通前先拦解读类
        return "commentary"
    if _is_gov(url) and (...):                         # 原 gov 快通不变
        return "policy"
```
`gate_one` 在 `v == "policy"` 分支前加:
```python
    if v == "commentary":
        return GateResult(ref, "commentary", 0.95, "title_commentary_marker", False, "commentary")
```
`_SYSTEM` 的 label 枚举加 `commentary`:
```python
    'Schema:{"label":"policy|commentary|non_policy_index|non_policy_news|non_policy_reply",'
```
`gate_one` LLM 分支里(`label == "policy"` 判定附近)加:
```python
    if label == "commentary":
        action = "commentary"
    elif label == "policy":
        action = "pass"
    elif conf < REVIEW_THRESHOLD:
        action = "review_queue"
    else:
        action = "reject"
```

- [ ] **Step 4: 跑测试确认通过(旧 gate 测试不回归)**

Run: `python3 -m pytest tests/l1_collect/test_policy_gate.py -v`
Expected: PASS(含旧 heuristic/gate_one 测试)

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/policy_gate.py tests/l1_collect/test_policy_gate.py
git commit -m "feat(l1): gate 加 commentary 标签(gov 快通前拦解读/答记者问)"
```

---

## Task 5: 泛化 `route_files(paths, dry)` 共用转换

**Files:**
- Modify: `scripts/_oneshot/route_interpretations.py`
- Test: `tests/l1_collect/test_route_files.py` (Create)

- [ ] **Step 1: 写失败测试**

`tests/l1_collect/test_route_files.py`:
```python
import textwrap
from pathlib import Path

def _write_policy(d: Path, name: str, title: str):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(textwrap.dedent(f"""\
        ---
        id: P_TEST_1
        title: {title}
        date: '2026-01-01'
        region:
          level: 省
          code: '320000'
          name: 江苏省
        provenance:
          url: https://swt.jiangsu.gov.cn/x.html
        type: policy
        ---
        ## 政策原文
        正文。
        """), encoding="utf-8")

def test_route_files_transforms_and_moves(tmp_path, monkeypatch):
    from scripts._oneshot import route_interpretations as ri
    pol = tmp_path / "policies"; com = tmp_path / "commentaries"
    com.mkdir(parents=True)
    _write_policy(pol, "解读.md", "《某细则》政策解读")
    monkeypatch.setattr(ri, "POLICIES", pol)
    monkeypatch.setattr(ri, "COMMENTARIES", com)
    moved = ri.route_files([pol / "解读.md"], index=[], dry=False)
    assert moved == 1
    assert not (pol / "解读.md").exists()           # 原文件移走
    out = (com / "解读.md").read_text(encoding="utf-8")
    assert "type: 政策评论" in out
    assert "commentary_kind: official" in out
    assert "## 政策原文" in out                      # body 保留

def test_route_files_dry_no_write(tmp_path, monkeypatch):
    from scripts._oneshot import route_interpretations as ri
    pol = tmp_path / "policies"; com = tmp_path / "commentaries"; com.mkdir(parents=True)
    _write_policy(pol, "x.md", "《Y办法》问答")
    monkeypatch.setattr(ri, "POLICIES", pol); monkeypatch.setattr(ri, "COMMENTARIES", com)
    n = ri.route_files([pol / "x.md"], index=[], dry=True)
    assert n == 1
    assert (pol / "x.md").exists()                   # DRY 不动
    assert not (com / "x.md").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l1_collect/test_route_files.py -v`
Expected: FAIL — `route_files` not defined

- [ ] **Step 3: 实现**

`route_interpretations.py`:把 `main()` 里 per-file 转换循环抽成函数(用模块级 `POLICIES`/`COMMENTARIES`,已存在);加 tracked 检测:
```python
import subprocess

def _is_tracked(p: Path) -> bool:
    rel = str(p).replace(str(VAULT) + "/", "")
    r = subprocess.run(["git", "-C", str(VAULT), "ls-files", "--error-unmatch", rel],
                       capture_output=True)
    return r.returncode == 0

def route_files(paths: list, index: list, dry: bool, now: str = "") -> int:
    """转换并移动给定文件 → commentaries/。tracked 走 git rm,untracked unlink。返回处理数。"""
    from datetime import datetime, timezone, timedelta
    now = now or datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    n = 0
    for p in paths:
        if not p.exists():
            continue
        fm, body = _front_body(p.read_text(encoding="utf-8", errors="ignore"))
        if not fm:
            continue
        title = str(fm.get("title") or "")
        tag = derive_tag(title, body)
        pid, _ = match_related(ref_policy_name(title), index)
        prov = fm.get("provenance") or {}
        fm["type"] = "政策评论"; fm["source"] = "l1_official"
        fm["commentary_kind"] = "official"; fm["business_tag"] = tag
        if prov.get("url"): fm["source_url"] = prov["url"]
        if fm.get("date"): fm["date_published"] = fm["date"]
        if pid:
            fm["related_policy"] = [pid]; fm["related_policy_source"] = "l1_title_match"
            fm["related_policy_confidence"] = 0.7; fm["related_policy_matched_at"] = now
        n += 1
        if dry:
            continue
        new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False)
        (COMMENTARIES / p.name).write_text(f"---\n{new_fm}---\n{body}", encoding="utf-8")
        if _is_tracked(p):
            subprocess.run(["git", "-C", str(VAULT), "rm", "-q", "--",
                            str(p).replace(str(VAULT) + "/", "")], check=False)
        else:
            p.unlink()
    return n
```
改 `main()`:构建 targets+index 后调 `route_files([p for p,_,_ in targets], index, DRY)`(`build_title_index` 的 skip 集仍排除 targets 自己)。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l1_collect/test_route_files.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/_oneshot/route_interpretations.py tests/l1_collect/test_route_files.py
git commit -m "refactor(l1): 抽 route_files 共用转换(tracked git rm/untracked unlink)"
```

---

## Task 6: `_gate_extracted_dir` 三路分流 + `ingest_commentary`

**Files:**
- Modify: `scripts/l1_collect/run_incremental.py`
- Modify: `scripts/l1_collect/ingester.py` (ingest_one 加 out_dir 形参)
- Modify: `scripts/l1_collect/step5_ingest.py` (ingest_extracted 透传 out_dir)
- Test: `tests/l1_collect/test_run_incremental.py`

- [ ] **Step 1: 写失败测试**

```python
import json
from pathlib import Path

def test_gate_dir_three_way_split(tmp_path):
    from scripts.l1_collect.run_incremental import _gate_extracted_dir
    ext = tmp_path / "ext"; ext.mkdir()
    (ext / "a.json").write_text(json.dumps(
        {"url": "https://x.gov.cn/a.html", "title": "某办法的通知", "body": "现就……"}),
        encoding="utf-8")
    (ext / "b.json").write_text(json.dumps(
        {"url": "https://x.gov.cn/zcjd/b.html", "title": "《某办法》政策解读", "body": "解读"}),
        encoding="utf-8")
    passed = tmp_path / "passed"; comm = tmp_path / "comm"
    quar = tmp_path / "q.jsonl"
    n_pass, n_comm, n_rej = _gate_extracted_dir(ext, passed, comm, quar, llm_fn=None)
    assert n_pass == 1 and n_comm == 1
    assert (passed / "a.json").exists()
    assert (comm / "b.json").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l1_collect/test_run_incremental.py::test_gate_dir_three_way_split -v`
Expected: FAIL — `_gate_extracted_dir` 返回 2 值 / commentary 未分流

- [ ] **Step 3: 实现**

`run_incremental.py` 改 `_gate_extracted_dir` 签名+逻辑(加 commentary_dir,返回三元组):
```python
def _gate_extracted_dir(ext_dir: Path, passed_dir: Path, comm_dir: Path,
                        quar_jsonl: Path, llm_fn) -> tuple:
    passed_dir.mkdir(parents=True, exist_ok=True)
    comm_dir.mkdir(parents=True, exist_ok=True)
    n_pass = n_comm = n_rej = 0
    rejects = []
    for jf in sorted(ext_dir.glob("*.json")):
        rec = json.loads(jf.read_text(encoding="utf-8"))
        gr = gate_one(ref=jf.stem, url=rec.get("url", ""), title=rec.get("title", ""),
                      body_head=(rec.get("body") or "")[:800], llm_fn=llm_fn)
        if gr.action == "pass":
            (passed_dir / jf.name).write_text(jf.read_text(encoding="utf-8"), encoding="utf-8")
            n_pass += 1
        elif gr.action == "commentary":
            (comm_dir / jf.name).write_text(jf.read_text(encoding="utf-8"), encoding="utf-8")
            n_comm += 1
        else:
            rejects.append({"file": jf.name, "url": rec.get("url", ""),
                            "title": rec.get("title", ""), **gr.to_dict()})
            n_rej += 1
    if rejects:
        quar_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(quar_jsonl, "a", encoding="utf-8") as f:
            for r in rejects:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return n_pass, n_comm, n_rej
```
**先给 ingest 路径加可选 `out_dir`(实测签名:`ingest_one` 写死 `ingester.POLICIES_DIR`,keyword-only;`ingest_extracted(in_dir, ingest_log)` 无 out_dir)**:
- `scripts/l1_collect/ingester.py` `ingest_one(*, ...)` 加形参 `out_dir: Path = POLICIES_DIR`;把构造文件名的 `POLICIES_DIR`(约 127/130 行 `fn = POLICIES_DIR / ...`)改成 `out_dir`。默认不变。
- `scripts/l1_collect/step5_ingest.py` `ingest_extracted(in_dir, ingest_log, out_dir=None)`:调 `ingest_one(..., out_dir=out_dir or POLICIES_DIR)`(从 `.ingester` import `POLICIES_DIR`)。默认不变。

加 commentary 入库函数(ingest_extracted 产 staging raw,再 route_files 转 commentaries):
```python
def _ingest_commentary(comm_ext_dir: Path, staging_dir: Path) -> int:
    """commentary extracted → ingest 成 staging raw(out_dir=staging)→ route_files 转 commentaries/。"""
    from scripts._oneshot.route_interpretations import route_files, build_title_index
    staging_dir.mkdir(parents=True, exist_ok=True)
    ingest_extracted(comm_ext_dir, staging_dir / "_ingest_log.jsonl", out_dir=staging_dir)
    paths = list(staging_dir.glob("*.md"))
    if not paths:
        return 0
    idx = build_title_index(skip_paths=set())
    return route_files(paths, index=idx, dry=False)
```
改 `_run_channel`:`_gate_extracted_dir(... comm_dir=sd/"comm_ext" ...)` 接三值,policy 照旧 ingest,commentary 调 `_ingest_commentary(sd/"comm_ext", sd/"comm_stage")`,summary 加 `ingested_commentary`;清理目录列表加 `comm_ext`/`comm_stage`。

> 注:Task6 单测只覆盖 `_gate_extracted_dir` 三路分流(确定性);`_ingest_commentary` 触 vault+git,**集成验证留 Task12 backfill**(不强行单测 vault 写)。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l1_collect/test_run_incremental.py -v`
Expected: PASS(旧 run_incremental 测试若调 `_gate_extracted_dir` 需同步改三值)

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/run_incremental.py scripts/l1_collect/ingester.py scripts/l1_collect/step5_ingest.py tests/l1_collect/test_run_incremental.py
git commit -m "feat(l1): gate 三路分流 + commentary 入库(ingest out_dir→route_files)"
```

---

## Task 7: `run_incremental --channel-type` 过滤

**Files:**
- Modify: `scripts/l1_collect/run_incremental.py`
- Test: `tests/l1_collect/test_run_incremental.py`

- [ ] **Step 1: 写失败测试**

```python
def test_select_channels_channel_type_filter():
    from scripts.l1_collect.run_incremental import _select_channels
    from scripts.l1_collect.channel_catalog import Channel, ChannelStatus
    def mk(ct, lvl="省"):
        return Channel(city="x", province="p", level=lvl, city_code="320000",
                       channel_type=ct, root_domain="d", list_url="u",
                       source="s", status=ChannelStatus.验证)
    chans = [mk("发改委"), mk("商务"), mk("市监"), mk("商务部", "国家")]
    sel = _select_channels(chans, ["province", "national"], channel_types=["商务", "市监"])
    types = {c.channel_type for c in sel}
    assert types == {"商务", "市监", "商务部"}   # 子串匹配:商务部 含"商务"
    assert "发改委" not in types
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l1_collect/test_run_incremental.py::test_select_channels_channel_type_filter -v`
Expected: FAIL — `_select_channels` 不接 channel_types

- [ ] **Step 3: 实现**

改 `_select_channels` + config + CLI:
```python
def _select_channels(channels, levels: list, channel_types=None):
    cn = {LEVEL_MAP.get(l, l) for l in levels}
    out = [c for c in channels if c.level in cn and c.status == ChannelStatus.验证]
    if channel_types:
        out = [c for c in out if any(ct in c.channel_type for ct in channel_types)]
    return out
```
`IncrementalConfig` 加 `channel_types: list = field(default_factory=list)`;`run_incremental` 调 `_select_channels(catalog, cfg.level, cfg.channel_types)`;`main()` 加 `ap.add_argument("--channel-type", default="")` 并 `channel_types=[s for s in a.channel_type.split(",") if s]`。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l1_collect/test_run_incremental.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/l1_collect/run_incremental.py tests/l1_collect/test_run_incremental.py
git commit -m "feat(l1): run_incremental --channel-type 过滤(定向 backfill)"
```

---

## Task 8: `audit_coverage_raw` 加「平台监管」列

**Files:**
- Modify: `scripts/_oneshot/audit_coverage_raw.py:THEMES`
- Test: `tests/l1_collect/test_audit_raw.py` (Create)

- [ ] **Step 1: 写失败测试**

`tests/l1_collect/test_audit_raw.py`:
```python
def test_themes_include_platform_regulation():
    from scripts._oneshot.audit_coverage_raw import THEMES
    assert "平台监管" in THEMES
    for kw in ("平台经济", "反垄断", "市场监管"):
        assert kw in THEMES["平台监管"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l1_collect/test_audit_raw.py -v`
Expected: FAIL — `'平台监管' not in THEMES`

- [ ] **Step 3: 实现**

`audit_coverage_raw.py` 的 `THEMES` 字典加一条:
```python
    "平台监管": ["平台经济", "反垄断", "反不正当竞争", "市场监管",
                "网络交易", "互联网平台", "经营者集中"],
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l1_collect/test_audit_raw.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/_oneshot/audit_coverage_raw.py tests/l1_collect/test_audit_raw.py
git commit -m "feat(l1): raw 覆盖审计加 平台监管 列"
```

---

## Task 9: `sweep_existing_commentary.py` 存量回扫(检测+DRY)

**Files:**
- Create: `scripts/_oneshot/sweep_existing_commentary.py`
- Test: `tests/l1_collect/test_sweep.py` (Create)

- [ ] **Step 1: 写失败测试**

`tests/l1_collect/test_sweep.py`:
```python
import textwrap
from pathlib import Path

def _pol(d, name, title):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(f"---\nid: P_X\ntitle: {title}\ntype: policy\n---\n## 政策原文\nx\n",
                          encoding="utf-8")

def test_sweep_detects_marker_titles(tmp_path, monkeypatch):
    from scripts._oneshot import sweep_existing_commentary as sw
    pol = tmp_path / "policies"
    _pol(pol, "a.md", "某省成品油管理办法")            # 真政策,不命中
    _pol(pol, "b.md", "《某办法》政策解读")             # 命中
    _pol(pol, "c.md", "国家能源局有关负责同志答记者问")   # 命中
    monkeypatch.setattr(sw, "POLICIES", pol)
    hits = sw.detect_commentary(pol)
    names = {p.name for p in hits}
    assert names == {"b.md", "c.md"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/l1_collect/test_sweep.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: 实现**

`scripts/_oneshot/sweep_existing_commentary.py`:
```python
"""存量回扫:扫全量 policies/ 命中 commentary marker 的 → DRY 报告 → apply via route_files。
带审核门:DRY_RUN=1(默认)只出报告;APPLY=1 才转 commentaries/。tracked 走 git rm。
"""
from __future__ import annotations
import os, re
from pathlib import Path
import yaml

from scripts.l1_collect.policy_gate import COMMENTARY_MARKERS
from scripts._oneshot.route_interpretations import route_files, build_title_index, _front_body

VAULT = Path.home() / "Documents/Zayn Main/政策分析"
POLICIES = VAULT / "0_raw/policies"
APPLY = os.environ.get("APPLY") == "1"

def detect_commentary(policies_dir: Path) -> list:
    hits = []
    for p in policies_dir.glob("*.md"):
        fm, _ = _front_body(p.read_text(encoding="utf-8", errors="ignore"))
        if not fm:
            continue
        if any(m in str(fm.get("title") or "") for m in COMMENTARY_MARKERS):
            hits.append(p)
    return hits

def main():
    hits = detect_commentary(POLICIES)
    print(f"存量 policies 命中 commentary marker: {len(hits)}  APPLY={APPLY}")
    for p in hits[:200]:
        print("  ", p.name[:70])
    idx = build_title_index(skip_paths={p.name for p in hits})
    n = route_files(hits, index=idx, dry=not APPLY)
    print(f"{'已转' if APPLY else '(dry)将转'} {n} → commentaries/")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/l1_collect/test_sweep.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/_oneshot/sweep_existing_commentary.py tests/l1_collect/test_sweep.py
git commit -m "feat(l1): sweep_existing_commentary 存量回扫(检测+DRY,审核门)"
```

---

## Task 10: gate golden + 校准加 commentary-recall

**Files:**
- Modify: `scripts/_oneshot/build_l1_golden.py`, `scripts/_oneshot/calibrate_l1_gate.py`
- 需 env:`set -a; . ~/.config/policy-pipeline/models.env; set +a`

- [ ] **Step 1: golden 加 commentary 类**

`build_l1_golden.py`:把本线 Task12 移到 `0_raw/commentaries/` 且 `commentary_kind: official` 的 18 篇,作 `gold_label="commentary"` 记录(url 取 `source_url`,title 取 title)。追加进 `golden_v1.jsonl`(每条 `{pid,url,title,body_head,gold_label:"commentary",is_planted:false}`)。

- [ ] **Step 2: 校准加断言**

`calibrate_l1_gate.py`:对 gold_label=="commentary" 的样本,跑 `gate_one`,统计 `commentary_recall = 命中 action==commentary / 总 commentary 数`。加输出 + 断言 `commentary_recall >= 0.9`。

- [ ] **Step 3: 跑校准(需 env)**

```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
cd ~/dev/政策分析-pipeline-l1-repair
python3 -m scripts._oneshot.build_l1_golden
python3 -m scripts._oneshot.calibrate_l1_gate
```
Expected: 输出含 `commentary_recall=1.00`(18 篇标题全含 marker → deterministic 必中)+ planted_recall 仍 ≥0.9。

- [ ] **Step 4: 提交**

```bash
git add scripts/_oneshot/build_l1_golden.py scripts/_oneshot/calibrate_l1_gate.py
git add -f state/l1_gate/golden_v1.jsonl state/l1_gate/gate_calibration.json
git commit -m "feat(l1): gate golden 加 commentary 类 + commentary-recall≥0.9 校准"
```

---

## Task 11(ops·CHECKPOINT): 跑商务/市监渠道发现

**Files:** Modify `scripts/_oneshot/expand_channels_l1.py`(加 commerce_market 模式)

- [ ] **Step 1: 接线 expand_channels_l1**

`expand_channels_l1.py`:import `commerce_market_targets`;加 env `DISCOVER_MODE=commerce_market` 分支 → `targets = commerce_market_targets(registry_path=...)`,对每个 `discover_one`,add-if-absent 进 catalog,`save_catalog`。沿用现有 add-if-absent + 打印逻辑。

- [ ] **Step 2: 真跑发现(需 env·孤儿化,~70 目标)**

```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
cd ~/dev/政策分析-pipeline-l1-repair
nohup caffeinate -i env DISCOVER_MODE=commerce_market \
  python3 -u -m scripts._oneshot.expand_channels_l1 \
  >state/l1_gate/discover_commerce_2026-06-08.log 2>&1 & disown
```

- [ ] **Step 3: 🛑 CHECKPOINT — 停,交用户审**

发现跑完,dump 商务/市监**验证**渠道表(机构/省/解析域名/list_url + 候选数)。**停**,交用户扫一眼:域名对不对、有无串味、哪些省落候选。用户确认后才进 Task 12。

---

## Task 12(ops): 定向 backfill + 覆盖审计前后

- [ ] **Step 1: 审计 pre(backfill 前)**

```bash
python3 -m scripts._oneshot.audit_coverage_raw --out state/l1_gate/audit_shangwu_pre.html
```

- [ ] **Step 2: 真跑 backfill(孤儿化·firecrawl 承重·仅商务/市监)**

```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
cd ~/dev/政策分析-pipeline-l1-repair
nohup caffeinate -i python3 -u -m scripts.l1_collect.run_incremental \
  --level national,province,city --channel-type 商务,市监 \
  >state/l1_gate/backfill_shangwu_2026-06-08.log 2>&1 & disown
```
背景 watcher 盯 `[run_incremental] DONE`。

- [ ] **Step 3: 审计 post + 质检**

```bash
python3 -m scripts._oneshot.audit_coverage_raw --out state/l1_gate/audit_shangwu_post.html
```
验:商务渠道出加油线政策(成品油/加油站)、市监出平台监管政策;抽查入库篇真为政策、日期不空;commentary 路由的篇确实落 commentaries/。

---

## Task 13(ops): 存量回扫 + commit 两仓

- [ ] **Step 1: 回扫 DRY → 用户审**

```bash
python3 -m scripts._oneshot.sweep_existing_commentary    # DRY,出命中列表
```
把命中列表交用户过目(确认都是真解读/答记者问,无误伤真政策)。

- [ ] **Step 2: apply(用户确认后)**

```bash
APPLY=1 python3 -m scripts._oneshot.sweep_existing_commentary
```

- [ ] **Step 3: commit 两仓(vault 先 tag)**

```bash
VAULT="$HOME/Documents/Zayn Main/政策分析"
git -C "$VAULT" tag pre-shangwu-backfill-2026-06-08
git -C "$VAULT" add 0_raw/
git -C "$VAULT" commit -m "data(l1): 商务/市监 backfill + 存量解读回扫 commentaries (2026-06-08)"
cd ~/dev/政策分析-pipeline-l1-repair
git add scripts/ tests/ state/T1_channels/channel_catalog.yaml
git add -f state/l1_gate/audit_shangwu_post.html
git commit -m "chore(l1·ops): 商务/市监渠道 + backfill 审计 (2026-06-08)"
```
注意 `git -C "$VAULT" status -z` 取 UTF-8 路径核对;models.env 勿提交。

---

## Self-Review(写完计划后自查)

- **Spec 覆盖**:组件1→Task1-2+11;组件2→Task3;组件3→Task4+6+10;组件4→Task5+9+13;组件5→Task7-8+12。✅ 全覆盖。
- **Type 一致**:`_gate_extracted_dir` 三值(Task6)→ `_run_channel` 接三值(Task6);`route_files(paths,index,dry)` 签名 Task5 定义、Task6/9 调用一致;`channel_type` ∈ {"商务","市监"}(Task1)→ `_institution_match` markers(Task2)/`--channel-type` 子串匹配(Task7)一致;`commerce_market_targets` root_domain=None(Task1)→ discover_one 域名未知支路(Task2)一致。
- **占位扫描**:无 TBD;唯一"待查"= Task6 `ingest_extracted` 是否有 `out_dir` 参(已给出加参指引,一行)。
```
