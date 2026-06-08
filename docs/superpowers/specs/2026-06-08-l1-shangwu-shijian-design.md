# L1 采集扩张:商务厅 + 市监局 + gate commentary 标签 — 设计 spec

> 2026-06-08。L1 采集修复线的后续专项。续 `feat/l1-capture-repair` 同 worktree/分支。
> 上游:[[l1-capture-repair-2026-06-06]](memory) · 前序 spec `docs/superpowers/specs/2026-06-06-l1-capture-repair-design.md`。

## Goal

把 L1 采集扩到两类现管线整个漏掉的机构,并堵住一个分类漏洞:

1. **商务厅**(成品油/加油站 = **加油业务线**):政策不含能源词、又无渠道 → 被关键词过滤 + 渠道缺失双重漏掉。
2. **市监局**(平台经济/反垄断/市场监管 = **企业背景维度**):公司是互联网/平台企业,这层是企业背景刚需;同样无能源词、无渠道。
3. **gate commentary 标签**:解读/问答/图解/答记者问当前因标题含"办法/细则"等政策信号词 + gov 域名被 heuristic 快通成 policy,混进 `0_raw/policies/`。让 gate 学第三标签 commentary,把它们路由到 `0_raw/commentaries/`;含一次带审核的存量回扫。

## 背景 / 现状(实测)

- **catalog 847 渠道**:发改委 417 / 能源局 194 / 政府网 225 / 国家级 11(各 1)。**省·市级商务厅/市监局 = 0**(只国家级 mofcom/samr 各 1)。
- **registry 164 域名**:商务 5、市监 ≈0(`amr/scjg` 域名几乎没有)。
- **scan KEYWORDS** 能源/油气为主:有"成品油"、**无"加油站"**;**完全无**平台经济/反垄断/市场监管/网络交易。
- **gate 漏洞**(`policy_gate._heuristic`):`_is_gov(url) and 标题含 POLICY_TITLE_SIGNALS(办法/细则/方案/通知…) → 直通 policy`,不进 LLM。解读/问答标题也带这些词 → 这样混进来的(本线 Task12 已清 18 篇)。
- **发现/扫描解耦**:`run_incremental` 不调发现,只 `load_catalog` + 选 `status==验证` 渠道扫;`discover_one` 只被 oneshot `expand_channels_l1.py` 调用 → 发现是一次性步骤,循环扫描路径不受发现改动影响。
- **现有渠道全是已知域名**:national 硬编码 `root_domain`,province 读 registry `domain`。

## 决策(已与用户拍定)

| # | 决策 | 取值 |
|---|------|------|
| D1 | 范围 | 三块一起:商务渠道+关键词 / 市监渠道+关键词 / gate commentary |
| D2 | 渠道层级 | 商务 = 国+省31+重点市;市监 = 国+省31 |
| D3 | gate commentary | 新采生效 + **回扫存量**(带审核门) |
| D4 | 实现方案 | A:就地扩展现有 `scripts/l1_collect/` |
| D5 | 缺域名怎么拿 | A1:**自动解析 + 机构名核验门 + 一次性 CHECKPOINT**(非手工域名表) |
| D6 | 采集姿态 | 沿用本次模式:Mac 改规则 + 跑一次小范围 backfill 验证补缺 → 收尾;大规模常态采集归 JP 服务线 |

## 架构:5 组件(全部就地扩展,不新建子系统)

| # | 组件 | 改哪 | 职责 |
|---|------|------|------|
| 1 | 域名无关渠道发现 | `channel_discovery.py` | 机构名+省(域名未知)→ Tavily→gov 过滤→LLM 选列表页→反推域名→机构名核验→probe |
| 2 | 关键词域扩展 | `step2_scan.py` | 全局 KEYWORDS 加 加油线 + 市场监管/平台两域 |
| 3 | gate commentary 标签 | `policy_gate.py` + 路由 | 标题/正文判 commentary,gov 快通前拦,路由 commentaries/ |
| 4 | 存量回扫(审核门) | 泛化 `route_interpretations.py` + 新 oneshot | 扫全量 policies/ → DRY → 人审 → 批量转 |
| 5 | 定向 backfill + 审计 | `run_incremental` + `audit_coverage_raw.py` | 跑新渠道补采 → 验产出 |

**数据流**:组件1(oneshot 发现+CHECKPOINT)产商务/市监渠道入 catalog → backfill 时组件2 召回 → 组件3 gate 分流(policy/commentary/reject)→ 落 policies/ 或 commentaries/。组件4 是一次性旁路清存量。

---

## 组件 1 — 域名无关渠道发现

### 新目标生成 `commerce_market_targets()`
类比现有 `province_targets_from_registry`,产出商务/市监目标(`root_domain` 可为 `None`):
- **商务**:31 省 + 重点市。机构名确定性派生 —— 省→`{省}商务厅`、直辖市(北京/天津/上海/重庆)→`{市}商务委员会`、重点市→`{市}商务局`。重点市 = `city_priority` 的加油线城市集(加油10)。
- **市监**:31 省,机构名 `{省}市场监督管理局`(直辖市同)。
- **暖启动**:registry 已有的 5 个商务域名直接填 `root_domain`,跳过解析;国家 mofcom/samr 用已有 `NATIONAL_TARGETS` 的硬编码域名。

### `discover_one` 扩「域名未知」支路
```python
if target.get("root_domain"):                       # 已知域名(现有路径不动)
    on_domain = [u for u in candidates if _same_domain(u, target["root_domain"])]
else:                                                # 新:域名未知
    on_domain = [u for u in candidates if _is_gov(u)]   # 只留 .gov.cn
picked = _llm_pick(target["city"], on_domain)        # LLM 见机构名选列表页
resolved_domain = target.get("root_domain") or (_host(picked) if picked else None)
list_url, pr = _first_verified(([picked] if picked else []) +
                               [u for u in on_domain if u != picked])  # 复用试下一候选(1ceb12a)
# 机构名核验门(仅域名无关路径):
ok_inst = _institution_match(resolved_domain, pr, target["channel_type"])
status = ChannelStatus.验证 if (pr.verdict == "ok" and ok_inst) else ChannelStatus.候选
```

### `_institution_match(domain, probe_result, channel_type)` — 防串味核验
- **域名标记**:商务类域名含 `swt` / `commerce` / `mofcom`;市监类含 `scjg` / `scjgj` / `amr` / `samr`。
- **或** probe 页标题/首屏含机构关键词:商务→"商务";市监→"市场监督" / "市监"。
- 任一命中 → 核验过。都不中 → 降候选(不进 backfill,留 CHECKPOINT 人看)。

### CHECKPOINT(一次性)
expand 跑完,把商务/市监**已验证**渠道(机构/省/解析域名/list_url)dump 成表,**停,交用户扫一眼**确认域名对、非串味,再开 backfill。同前序 Task10 CHECKPOINT 款。

### 防串味四重(汇总)
① Tavily query 带机构名(`"江苏省商务厅 政策文件 通知公告"`)② gov-only 过滤 ③ LLM-pick 见机构名 ④ `_institution_match` 核验门 + CHECKPOINT 人眼。`url in candidates` 守卫(现有)挡机场注入。召不到列表页的省落候选(长尾,记日志,不强造)。

---

## 组件 2 — 关键词域扩展

`step2_scan.KEYWORDS` 全局并集加两域(沿用"宽进 + 末端 LLM 门控"):
- **加油线**:`加油站` `成品油零售` `油品经营` `加油` `燃油`(`成品油` 已有)
- **市场监管/平台(企业背景)**:`平台经济` `反垄断` `反不正当竞争` `市场监管` `网络交易` `互联网平台` `经营者集中` `公平竞争审查` `价格监管`

**克制**:不收 `企业登记` 等过宽词(大量召回办事指南);召回锚点够即可,精度交末端 gate。全局并集会让发改委等渠道也多扫几条含这些词的 → gate 兜掉,可接受(盯 gate-reject 率)。

---

## 组件 3 — gate commentary 标签

### `policy_gate.py`
```python
COMMENTARY_MARKERS = ("政策解读", "解读材料", "文字解读", "答记者问",
                      "一图读懂", "图解", "图读", "问答")
```
- `_heuristic`:在 `_blacklisted` 之后、**gov 快通之前**插:`if any(m in title for m in COMMENTARY_MARKERS): return "commentary"`。
- `gate_one`:`v=="commentary"` → `GateResult(label="commentary", confidence=0.95, evidence="title_commentary_marker", used_llm=False, action="commentary")`。
- **LLM 兜底(纵深)**:`_SYSTEM` schema 的 label 枚举加 `commentary`(接住标题无 marker、正文是解读口径的);`gate_one` 里 `label=="commentary"` → `action="commentary"`。

### 路由(`run_incremental` / ingester)
`action=="commentary"` → 落 `0_raw/commentaries/`,复用 `route_interpretations` 的加工:
`type: 政策评论` + `source: l1_official` + `commentary_kind: official` + `business_tag`(内容派生)+ best-effort `related_policy`(《》标题匹配)+ 保留 body/provenance。

### 门校准
本线 Task12 移走的 18 篇官方解读 = **commentary golden**。`calibrate_l1_gate` 加一条断言:**commentary-recall ≥ 0.9**(同 planted-recall 套路),达标才算门上岗。

---

## 组件 4 — 存量回扫(带审核门)

- **泛化 `route_interpretations.py`**:把"识别 + frontmatter 加工 + 移动"抽成吃**显式文件列表**的函数(现仅吃 `untracked_policies()`)。
- **新 oneshot `sweep_existing_commentary.py`**:扫**全量** `0_raw/policies/`(873 tracked + 158 新)命中 `COMMENTARY_MARKERS` 的标题 → **DRY 报告**(文件 / 标题 / 拟 business_tag / 拟 related_policy)→ 用户过目 → apply:**tracked 走 `git mv`(保 history),untracked 平移**。
- **P_1900 答记者问** 会在此被抓 → 转 commentaries(Task12 的日期修复保留)。
- 分工:组件3 防**新**混入,组件4 清**存量**已混入;后者一次性旁路。

---

## 组件 5 — 定向 backfill + 审计

### Backfill(一次性、孤儿化)
- 渠道发现 + CHECKPOINT 过后,`run_incremental` 跑新渠道。`nohup caffeinate -i <cmd> >log 2>&1 & disown`,firecrawl 承重(选 C,可迁 JP)。
- **`_select_channels` 加可选 `channel_type` 过滤**(`--channel-type 商务,市监`):现仅按 level 选会连发改委一起重扫;加类型过滤让定向 backfill 干净。商务跑 国+省+重点市,市监跑 国+省。

### 审计(前后对比)
- 扩 `audit_coverage_raw.py` 的 `THEMES`:加油列已含成品油/加油站;**加「平台监管」列**(平台经济/反垄断/市场监管/网络交易)。验商务渠道出加油线政策、市监出平台政策。pre(现 ≈0)→ post。

---

## 测试(TDD,网络全 mock,沿用现有 86 测试模式)

- **组件1**:`commerce_market_targets`(直辖市→委命名;registry 暖启动填域名);域名无关 `discover_one`(Tavily 返 gov+非gov → gov 过滤 → pick → 反推域名 → `_institution_match` 过/降候选);`_institution_match`(域名标记命中 / 页标题命中 / 都不中→False)。
- **组件2**:加油站/平台经济标题过 `KEYWORDS` 过滤;无关标题不过。
- **组件3**:`_heuristic` 对"《X办法》政策解读"在 gov 快通前返 commentary;`gate_one` action=commentary;LLM label=commentary 映射 action;校准 commentary-recall。
- **组件4**:`route_interpretations` 泛化吃文件列表;`sweep` 跨 tracked+untracked 检出 marker,DRY 不写盘。
- **组件5**:`_select_channels` channel_type 过滤;`audit_coverage_raw` 平台监管列计数。

## 风险 / 交接

1. **市监 L2 无家**(交接):平台/企业背景不在 ②-B 13-theme 词表 → 采下来"先停 raw",等 ②-B 加"平台合规/企业背景"维度才进 L2 分析。L1 只按白名单采 raw、不打业务标签。**本线仅标记,不解。**
2. **域名无关串味**:gov 过滤 + `_institution_match` + CHECKPOINT 三重兜;召不到的省落候选(长尾,记日志,不强造)。
3. **关键词过召**:末端 gate 兜;盯 gate-reject 率,过高则收窄词表。
4. **commentary marker 误伤**:罕见真政策标题含"问答/图解"(如《问答手册》以通知印发)→ golden 校准 + CHECKPOINT 抓极端;deterministic marker 为主、LLM 兜底;误伤可从 commentaries/ 移回(同回收路径)。
5. **geo**:firecrawl 承重已选 C,Mac 产物可迁 JP。

## 不在范围(Out of scope)

- ②-B 给市监/企业背景加 theme 维度(下游,见风险1)。
- 国家级 miit/mohurd/chinatax 的列表页召回(不同根因:Tavily 召不到列表页 + 硬 JS 反爬;另案)。
- 标准委(sac)(用户已拍跳过)。
- 大规模常态采集 → JP 服务线(D6)。

## Ops 纪律

续 `feat/l1-capture-repair` 同 worktree/分支;`~/.config/policy-pipeline/models.env` 凭据**勿提交/勿写摘要**;别碰 `~/dev/政策分析-pipeline`(service-deploy 线);raw 写走 §C(确定性字段可改+provenance);`git -C vault status -z` 取 UTF-8 路径(默认 quotepath 转义《》【】" 会漏);后台长抓孤儿化。
