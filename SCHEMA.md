---
title: 政策分析数据 Schema(契约文档)
version: v1.0 (post-split,2026-05-08)
authority: 本文件是 vault 与 pipeline 之间的唯一契约。所有读写以本文为准。
---

# Schema 契约

> 本文件定义 vault 里的数据形态。pipeline 通过本契约读写 vault,**不通过反推老代码理解 schema**。
> Vault 同步保留一份 SCHEMA.md,内容与本文件一致。

---

## 0. 哲学

1. **Raw immutable**:`0_raw/` 一旦入库,frontmatter 业务字段 + body 不可修改。例外字段白名单见 §C。
2. **派生分层**:对 raw 的解读、评分、关系判断、LLM 生成内容,统一落派生层(`1_extracted/` / `2_crystallized/` / `_meta/business_view/`)。
3. **LLM 生成 = 派生**:任何 LLM 输出都是派生,即便看起来"客观"(如摘要、规范化标题)。
4. **可追溯**:每个派生产物必须能指回 raw 源。
5. **可重现**:同 raw + 同规则 → 同派生。

---

## 1. 目录契约

```
vault/
├── 0_raw/
│   ├── policies/*.md          政策 raw
│   ├── commentaries/*.md      评论 raw
│   ├── _archive/              归档 raw(版本替换、quality drop)
│   └── _duplicates/           dedup 隔离区
│
├── 1_extracted/               L2 通用派生(公开)
│   ├── policy_summaries.jsonl 政策客观摘要(每行 by policy_id)
│   ├── relations/*.jsonl      9 类关系 + _index_by_policy/ 反链页
│   ├── entities/              canonical 实体 + 反链页
│   ├── opinions/              评论观点 + 政策舆论矩阵
│   └── commentary_audit/      评论审计
│
├── 2_crystallized/            L3 结晶层
│   ├── themes/                主题结晶页(每主题 4 文件)
│   ├── regions/               区域聚合页
│   ├── _global_index.md       全局大盘
│   └── _reports/              月报渲染产物
│
├── 3_lints/                   lint 报告(daily / weekly)
│
├── _meta/
│   ├── business_view/*.yaml   L2 业务私有派生(评分 / 影响分析 / 行动建议)
│   ├── themes_registry.yaml   主题 canonical 词表
│   ├── entities/registry.yaml 实体 canonical 词表
│   └── (其他配置数据)
│
├── 00 背景资料/                项目背景与配置数据
│   ├── 渠道目录.md
│   ├── 优质公众号白名单.md
│   ├── 政策重要性打分体系.md
│   └── 滴滴能源-政策分析背景.md
│
├── SCHEMA.md                   本文件副本
├── CLAUDE.md                   vault 自身的提示(只读数据仓)
└── 开发日记/                   人工工作日志
```

**写权约定**:

| 路径 | Pipeline 写 | Pipeline 读 | Vault 内人工写 |
|---|---|---|---|
| `0_raw/policies/` | 仅入库脚本(整体写,不就地编辑) | ✓ | ✗(原则上禁止) |
| `0_raw/commentaries/` | 入库脚本 + 关系回填脚本(白名单字段) | ✓ | ✗ |
| `1_extracted/` | ✓ 整体重写 | ✓ | ✗ |
| `2_crystallized/` | ✓ 整体重写 | ✓ | ✓ 允许人工 polish |
| `_meta/business_view/` | ✓ 整体重写 | ✓ | ✗ |
| `_meta/themes_registry.yaml` 等 canonical | ✓ append + review | ✓ | ✓ 允许人工调 |
| `00 背景资料/` | ✗ | ✓ | ✓ 人工维护 |
| `开发日记/` | ✗ | ✗ | ✓ 人工写 |
| `SCHEMA.md` / `CLAUDE.md` | ✗ | ✓ | 同步本文件 |

---

## 2. Policy frontmatter(`0_raw/policies/*.md`)

```yaml
---
# === 身份(必填) ===
id: P_2024_NDRC_718              # P_<year>_<issuer_short>_<num/hash>
aliases:
  - P_2024_NDRC_718              # Obsidian 内部 alias 解析需要
title: 关于推动车网互动规模化应用试点工作的通知
official_number: 发改办能源〔2024〕718号    # 无文号留空字符串
issuer:
  - 国家发展改革委
  - 国家能源局                   # 多机构联合发文用数组
date: '2024-01-05'

# === 区域(必填) ===
region:
  level: 国家                    # 国家 / 省 / 市 / 区
  code: '000000'                # 行政区划代码,国家级用 000000
  name: 全国

# === 来源链(provenance,必填) ===
provenance:
  url: https://www.ndrc.gov.cn/...
  source_type: A                 # A 政府/B 媒体/C 公众号/D PDF/E 会议讲话
  fetched_via: firecrawl         # 或 fetched_method(legacy 别名),见 §F
  fetched_at: '2026-04-25T11:07:53'
  collected_by: policy-watch
  collected_mode: cron-daily     # cron-daily / url-intake / build-phase-manual
  confidence: 0.95
  # ↓ 以下子键为审计派生(可选,见 §F drift register)
  audit_run: ~
  candidate_priority: ~
  src_count: ~

# === 派生辅助(可选) ===
issuer_canonical:
  - ndrc                         # 渠道目录 URL 映射,deterministic

type: policy                     # 枚举:policy / core_policy / 核心政策(同义,见 §F)
subtype: ~                       # 子类(可选)

# === Top-level confidence(legacy 字段,见 §F) ===
confidence: 0.95                 # 或 high / medium / low(legacy 字符串值)

# === Dedup 标记(可选,仅 _duplicates/) ===
dup_aliases: []
dedup_at: ~
dedup_rule: ~
_duplicate_of: ~
_duplicate_reason: ~
---
```

### 字段白名单(强制约束)

**只允许**上述字段(含 §F 列出的 legacy 别名)。**禁止**:`tags` / `重要性` / `行动分类` / `价值标签` / `scores` / `影响分析` / `行动建议` / `related` / `business_tags` 等业务派生字段。这些字段已下沉到 `_meta/business_view/{pid}.yaml`。

### Body 约束

`0_raw/policies/*.md` body **只允许** `## 政策原文`(及其 ### 子段,字面摘抄)。

**禁止**段:
- `## 摘要`(LLM 生成,落 `1_extracted/policy_summaries.jsonl`)
- `## 初步影响分析` / `## 六维评分` / `## 业务关联` / `## 跟进建议` / `## 战略地位映射`(全部业务派生,落 `_meta/business_view/`)

### id 生成规则

```
P_<year>_<issuer_short>_<num_or_hash>
```

- `<year>`:date 字段年份。无 date 用 `1900` 占位(标记日期未抽到,等补)
- `<issuer_short>`:URL 映射到 canonical(NDRC, NEA, MIIT, MOF, MEE, MOHURD, SC, GO, PBOC ...);省级用 `BJ_DRC` / `SH_DRC` 等;无机构用 `OTHER<HASH>`
- `<num>`:文号尾号;无文号用日期+标题哈希前 8 位
- 碰撞:加 `_a` `_b` 后缀

---

## 3. Commentary frontmatter(`0_raw/commentaries/*.md`)

```yaml
---
title: 评论标题
type: 政策评论                    # 固定枚举(可选)
source_type: B                    # A/B/C/D(与 policy 同枚举,可选)
source_account: 电动汽车观察家     # 公众号或媒体名;web 媒体可为域名
source_url: https://mp.weixin.qq.com/s/...
date_published: '2026-01-22'      # 发表日期(可 null)
fetched_at: '2026-04-28 20:52:51+08:00'
commentary_type: A                # A 解读 / B 分析 / C 案例 / D 数据 / E 转发(枚举)
business_tag: charging            # power / charging / gas / cross
source: wewe-rss                  # wewe-rss / tavily / firecrawl / wechat-article-to-markdown
confidence: 0.9                   # 权威号 0.9 / 行业媒体 0.7 / 匿名 0.5

# === provenance(嵌套,从 v2→v3 迁移残留,可选) ===
provenance:
  confidence: 0.9
  collected_by: policy-watch
  fetched_at: ...
  fm_v3_migrated_at: ~
  fm_v3_migrated_from_v2: ~

# === 关系字段(白名单例外,见 §C) ===
related_policy: ~                 # [[P_xxx]] 或数组(可空)
related_policy_source: ~          # B1_official_number / B2_title_fuzzy / B3_llm / B4_llm_body_review / tavily_pull / manual
related_policy_confidence: ~      # 关系附属置信度(可选)
related_policy_matched_at: ~      # 关系匹配时间戳(可选)
not_policy_related: ~             # true=已确认无政策可关联(化工/法律/海外行情等)
---
```

### Commentary 入库后的特殊性

评论 frontmatter 的关系字段(`related_policy` / `related_policy_source` / `not_policy_related`)允许 pipeline 后置回填——这是 `Raw immutable` 的**白名单边界例外**(详见 §C)。

---

## 4. 业务派生 yaml(`_meta/business_view/{pid}.yaml`)

```yaml
pid: P_2024_NDRC_718

# === 评分(必填) ===
scores:
  D1: 5                  # 业务关联度
  D2: 4                  # 直接影响度
  D3: 4                  # 发布主体层级
  D4: 4                  # 紧迫性
  D5: 4                  # 实操性
  D6: 5                  # 机会窗口
重要性: 4                # round(D1×0.4 + D2×0.4 + D3×0.2)
行动分类: A              # A 趁早 / B 研究 / C 跟进 / D 跟踪
价值标签:                # 多选: 合规 / 机会 / 壁垒 / 趋势
  - 合规
  - 机会

# === 影响分析(可选,D1≥3 时填) ===
影响分析:
  加油: 加油业务影响描述
  充电: 充电业务影响描述
  电力_储能_V2G_交易: 电力业务影响描述
  乡村: 乡村方向影响描述

# === 行动建议(可选,D1≥3 时填) ===
行动建议:
  - 'A 趁早: 具体动作'
  - 'B 研究: 具体动作'

# === 一句话精髓(可选) ===
didi_impact_one_liner: 业务一句话精髓(≤25 字)

# === 可追溯字段(必填) ===
extracted_at: '2026-04-29'
extracted_by: scripts/l2_derive/derive_business_view.py
extracted_model: claude-opus-4-7
sanitized_from: 0_raw/policies/{filename}.md     # 指回 raw

# === Archive 标记(可选,综合分 <3 时) ===
archive: low_score
```

---

## 5. L2 通用派生

### 5.1 政策摘要 `1_extracted/policy_summaries.jsonl`

每行一条:
```json
{
  "policy_id": "P_2024_NDRC_718",
  "summary": "2-3 句客观摘要,描述政策范围/对象/截止日/数量目标",
  "summary_one_liner": "≤25 字精髓",
  "reading_value": "≤25 字阅读价值",
  "extracted_at": "2026-04-29T...",
  "extracted_by": "scripts/l2_derive/derive_business_view.py"
}
```

### 5.2 关系 `1_extracted/relations/<rel>.jsonl`

9 类关系,每类一份独立 jsonl。

| rel | 含义 | 抽取方式 |
|---|---|---|
| `supersedes` | 显式废止 | regex 文号 + LLM 验证 |
| `iterates` | 升级/v2 | LLM 标题与摘要对比 |
| `extends` | 范围扩展(试点 → 全国) | LLM + region 跳变 |
| `clarifies` | 实施细则/操作指引 | 标题正则 + LLM |
| `references` | 引用但不修改 | regex 文号交叉引用 |
| `aligns_with` | 不同部门同主题对齐 | LLM + 主题相似度 |
| `conflicts_with` | 内容冲突(罕见) | LLM 仅扫高分政策对 |
| `cites_basis` | 显式"作为制定依据"引用 | 位置过滤(opening 800 字符)+ LLM 语义判定 |
| `derives_from` | 国家级追溯(省/市派生自国家级) | Step 5C LLM 副产物 |

**通用行格式**:
```json
{
  "from": "P_2024_NDRC_718",
  "to": "P_2022_NDRC_xxx",
  "rel": "supersedes",
  "evidence": "原文摘录...",
  "confidence": 0.95,
  "extracted_by": "regex+llm",
  "extracted_at": "2026-04-25T..."
}
```

**`cites_basis` 扩展字段**:`location` ∈ {opening, body, supplementary},`semantic` ∈ {basis, clause_ref, context_mention}。

**`derives_from` 扩展字段**:`linkage_type` ∈ {直接落地, 借鉴框架, 主题对应},`to_title`(LLM 原文,即使 to=null)。

### 5.3 反链页 `1_extracted/relations/_index_by_policy/{pid}.md`

每个有入向或出向边的政策一份。结构:

```markdown
---
policy_id: P_xxx
title: ...
inbound_edge_count: N
outbound_edge_count: M
last_updated: ...
---

# 入向反链:P_xxx
## 被引为依据 (cited_as_basis_by) — N
## 被废止 (superseded_by) — N
## 被迭代 (iterated_by) — N
## 被引用 (referenced_by) — N
## 被扩展 / 被细化 / 被对齐 / 被冲突 / 被落地

# 出向引用:P_xxx
## 引用了 / 细化了 / 迭代了 / ...
```

**出向 → 入向命名表**:

| 出向 jsonl | 入向 section |
|---|---|
| supersedes | superseded_by |
| iterates | iterated_by |
| extends | extended_by |
| clarifies | clarified_by |
| references | referenced_by |
| aligns_with | aligns_with_by |
| conflicts_with | conflicts_with_by |
| cites_basis | cited_as_basis_by |
| derives_from | landed_by |

### 5.4 实体 `1_extracted/entities/`

5 类实体:`org` / `stakeholder` / `concept` / `theme` / `region`。

Canonical 注册在 `_meta/entities/registry.yaml`(或 vault 内等价位置,以实际 vault 状态为准)。

实体页 `1_extracted/entities/<type>/<id>.md` 完全派生,不允许手写。

### 5.5 评论观点 `1_extracted/opinions/<policy_id>.md`

`polarity` 4 档:`supportive` / `critical` / `neutral` / `mixed`。

舆论矩阵 = 共识(≥3 独立来源同向)+ 分歧 + 中性观察 + 待跟进。

---

## 6. 主题结晶 `2_crystallized/themes/<theme>/`

每主题 4 文件:
- `overview.md` — 综述 + 关键政策 Top N + 时间脉络要点
- `timeline.md` — 政策时间线
- `regional-coverage.md` — 区域覆盖矩阵 + 空白发现
- `opinions-summary.md` — 同主题舆论元分析

**`2_crystallized/_reports/`(月报渲染产物)**:本阶段**不再维护**。既存 March 月报作为历史数据保留,不删但不更新。

---

## C. Raw 不可变的边界例外(白名单)

`0_raw/` immutable 原则有合法例外。**仅以下字段**允许 pipeline 后置回填到 raw frontmatter:

### Commentary 关系字段
- `related_policy`(指向 vault 内政策的链接)
- `related_policy_source`(关联来源标识:B1/B2/B3/manual/tavily_pull)
- `not_policy_related`(无政策可关联标记)
- `commentary_type`(枚举分类)

### Deterministic 身份字段重算(v1.1 新增)

允许 pipeline 重算并就地更新以下身份字段,**仅当新值由确定性规则从已有 metadata 计算得出**(非 LLM 自由生成):

- `id`(由 `date.year` + `issuer_short` + `num/hash` 计算)
- `aliases`(随 `id` 同步更新,**旧 id 必须保留在 aliases 数组中**以保持 Obsidian 反链可解)
- `date`(从 URL path / 正文 / H1 等结构化位置抽取)
- `region.level` / `region.code` / `region.name`(由 `issuer_canonical` 或 URL 域名 lookup)
- `issuer` / `issuer_canonical`(由 URL 域名 / 正文 H1 抽取后查 canonical 表)

每次重算必须在 `provenance` 中记录审计字段:

- `<field>_fixed_at`(ISO 时间戳)
- `<field>_fixed_method`(枚举:`url_path_pattern` / `url_path_month_only` / `url_year_only` / `body_publish_time` / `body_chinese_date` / `title_extract` / `domain_lookup` / `id_recompute_from_metadata` / `combined`)
- `<field>_fixed_from`(原值)
- `<field>_fix_confidence`(0–1,可选)

对 `id` 字段额外要求:

- 重算后 `aliases` 数组**必须**同时包含旧 id 和新 id(Obsidian 反链兼容)
- 文件名保留不变(vault 文件名是中文标题哈希,与 id 解耦)
- 派生层引用旧 id 的位置由专用 oneshot 同步重指,**不与 raw 改动同 commit**

### 判定标准
允许写入 raw frontmatter 的字段必须**同时**满足:
1. 是「指向 vault 已有文档的链接」、「枚举型分类标签」或「deterministic 派生的身份字段」
2. **不是** LLM 生成的自由文本(摘要 / 影响分析 / 语义标签)

凡 LLM 生成的自由文本一律落派生层。

### 新增白名单字段流程
新字段加入白名单需走 SCHEMA.md 修改流程,有评审记录。**不允许"约定俗成"扩张**。

---

## D. 重抓重入(版本替换,不就地覆盖)

发现 raw 抓取错误时,**唯一合法的修改路径是重抓**:
1. 重新抓取该政策正文
2. 旧版迁 `0_raw/_archive/policies/`,文件名加日期后缀
3. 新版用 `_v2` 后缀入新位置(避免 id 碰撞)
4. 派生层重新跑该 pid

不就地编辑 raw frontmatter / body。

---

## F. Drift Register(legacy 字段 + 迁移目标)

vault 当前内含一些字段,与"理想 schema"有出入,但是真实存在的数据。本 register 显式标注,避免静默 drift。

### Policy frontmatter drift

| 字段 | 现状 | 目标 | 处置 |
|---|---|---|---|
| top-level `confidence` | 存在,值 `0.95` 数字 / `medium` 字符串混用 | 仅保留 `provenance.confidence` 数字 | 保留兼容,新写入只写 `provenance.confidence`;未来一次性归一 |
| `provenance.fetched_method` | 部分政策用 `fetched_method`,部分用 `fetched_via` | 统一 `fetched_via` | 保留兼容,validator 接受两个,新写入只写 `fetched_via` |
| `provenance.audit_run` / `candidate_priority` / `src_count` | tier A/B 补抓时引入的审计派生字段 | 移到工程仓 state,不进 raw | 保留兼容,后续 cleanup pass 把它们抽出去 |
| `type: policy` vs `核心政策` | 两种值并存 | 统一英文枚举 `policy` / `core_policy` | 保留兼容,新写入只用英文 |

### Commentary frontmatter drift

| 字段 | 现状 | 目标 | 处置 |
|---|---|---|---|
| `provenance` 嵌套 | v2→v3 迁移残留,部分 commentary 还在用 | commentary 不需要嵌套 provenance | 保留兼容,新评论入库不再写 provenance |
| `fm_v3_migrated_at` / `fm_v3_migrated_from_v2` | v2→v3 迁移标记 | 迁移完成后删 | 等 commentary 全量重写时清 |
| `related_policy_confidence` / `related_policy_matched_at` | B4 LLM 判定时附加的置信度/时间 | 应进派生层,不在 raw frontmatter | 保留兼容,后续把这些迁到 `1_extracted/commentary_audit/` |
| **缺 `title` 字段** | ~67 / 283 评论 frontmatter 缺 title(标题在文件名) | 必填 title 字段 | **数据缺陷**,后续 cleanup pass 从文件名补回 |

### 严重违反(应清理但作为 cleanup pass 跑,不阻塞)

| 违反 | 现状 | 来源 | 处置 |
|---|---|---|---|
| Policy 含 `tags` + `classification` 字段 | ~81 / 1020 政策(7.9%) | `isolated_classification` 任务 LLM 派生倒灌 raw | **违反 LESSONS A2/A3**,需 cleanup pass 清出。`classification` 派生信息迁到 `1_extracted/commentary_audit/` 或类似派生层 |
| Commentary 缺 `title` | ~67 / 283 评论(23.7%) | 入库时未抽 title | cleanup pass 从文件名补回 |
| Commentary 留有 policy 字段(reclassified) | ~14 / 283 评论 | 原政策被 reclassify 为评论(`_migrated_from: policies`),policy frontmatter 字段未清 | cleanup pass 删除 policy-only 字段(id/region/issuer/issuer_canonical/official_number/tags/_migrated_*/_review_needed_*) |

### Drift 处置纪律

1. SCHEMA validator 接受 drift 字段(标 `legacy`,不报错)
2. **新写入**严格按"目标"写,不写 legacy 别名
3. Drift cleanup 是独立任务,有 dedicated cleanup pass(不是日常工作的副作用)
4. Drift 字段在派生层不被依赖——派生层只读"目标"字段,legacy 字段视为不存在

---

## E. Schema 演进规则

1. 本文件每次修改维护 `## Changelog` 段(下方)
2. 重大修改先在 pipeline 提案,vault SCHEMA.md 同步
3. 字段废弃用"废弃"标记保留 ≥1 个版本周期,不立即删
4. 不允许"边干边偷偷改 schema 不同步本文件"

---

## Changelog

### v1.1 — 2026-05-12(身份字段重算白名单)

- §C 新增 "Deterministic 身份字段重算" 子节,显式授权 `id` / `aliases` / `date` / `region` / `issuer` 在确定性规则下就地重算
- §C 判定标准第 1 条扩展为接受 "deterministic 派生的身份字段"
- driver: T3 P_1900 id drift 修复任务,proposal 与执行细节见 `docs/proposals/schema-c-id-recompute.md` 和 `state/T3/`
- §F 未变(vault 中已存在的 `date_fixed_*` / `region_fixed_*` / `issuer_fixed_*` 字段从未在 §F 显式登记,本次合并后归位到新白名单,§F 不需删除条目)

### v1.0 — 2026-05-08(C 路径切换)

- 从 `_meta/schema_v3.md`(2026-04-25 起草)抽取并合并 2026-04-29 解耦后的 split 现状
- L1 frontmatter 白名单显式化(去除 tags / scores / 重要性等)
- L1 body 限定 `## 政策原文` 段
- business_view 字段集对齐当前 vault 实际产出
- 9 类关系(含 derives_from)正式入 schema
- 评论关系字段作为 raw 不可变边界例外列入 §C 白名单
- 重抓重入流程显式化(§D)
