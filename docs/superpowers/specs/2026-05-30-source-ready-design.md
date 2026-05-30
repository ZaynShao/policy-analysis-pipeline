---
title: 设计 spec · ①源到位（source-ready）
date: 2026-05-30
status: 设计已获用户口头批准，待用户复核本文件
node: 顶层设计四节点中的 ①（源 → 归属 → 分析 → 消费）
charter: docs/2026-05-30-top-level-design-v2.html
assessment: docs/reviews/2026-05-30-meta-design-assessment.html
---

# ①源到位 · 设计 spec

## 0. 背景与目标

顶层设计 v2（见 charter）把项目重心从"重型 ETL 知识图谱"换成"干净源 + 按需视图"，并定下四个"到位"节点：**源 → 归属 → 分析 → 消费**，每个节点有自己的 done-gate，一层叠一层，不允许"③做完发现①不牢又回头重来"。

本 spec 只覆盖 **①源到位**。目标一句话：**把存量 L1 一次性审计干净并冻结一个 checkpoint，把分析框架收成 agent 可调用的结构化文件**——为后续 ②归属 / ③分析（关系重建、消灭孤岛）提供可信底座。

**为什么①必须先做**：探针（2026-05-18）证明 L1 仍混着新闻稿，会被当政策连进关系网、污染整张图。现成的 `news_filter` 只在 T1 新采集时用，**从没回扫过存量 999 篇**。在没审计干净的 L1 上重建关系 = garbage in。

## 1. 范围

### 在范围（本 spec）
- **子项 a**：L1 干净审计（回扫存量 999 政策）+ 冻结 checkpoint
- **子项 b**：canonical 词表校验（themes / entities registry）
- **子项 c**：分析框架结构化（月报原型 / fact-check / 四维 / 打分 → agent 可 load 文件）

**构建顺序**：a 关键路径先做；b、c 较轻，随后/并行，同进本节点交付。

### 不在范围（属其他节点，本 spec 不碰）
- ❌ 关系图重建、孤岛消灭、business_view、结晶页（→ ②③）
- ❌ index / API / L3 产出（→ ④）
- ❌ **不回头 remap 派生层**：派生层将在 ③整体重建，本节点只动 raw（审计）+ 留派生层不动。这正是 charter "零补丁、整体重建" 的体现——不迁化石。
- ❌ 不重抓 raw（老 raw 是资产，不可重抓）
- ❌ 探针里的"自环""doc_num 多匹配"是关系层的病 → ③

## 2. 成功标准（done-gates）

| 子项 | 算到位的判据 |
|---|---|
| a | L1 lint 全过；新闻稿 flagged 经 ≥95% 抽样精度后已迁 `_archive`；id-prefix 与 issuer 字段一致；URL/文号无重复；残留 P_1900 收口（剩 1 篇山西进 backlog）；打出 git tag `clean-L1-<date>` + 审计报告 |
| b | themes / entities registry 无重复 id / 无冲突 alias；registry 内部自洽 |
| c | 打分体系 / 四维决策框架 / fact-check 规则 / 月报蓝图 各成一个结构化、可被 LLM 直接 load 的文件，且有一个 index 索引它们 |

## 3. 子项 a · L1 干净审计

### 3.1 两阶段流程（dry-run 先行，绝不直接动数据）

```
阶段1 dry-run（零变更）         阶段2 抽样校 + 应用
─────────────────────          ──────────────────────
4 类检查 → 报告                  对判断型输出抽样校精度
        + proposed_changes      ├─ ≥95% → 自动应用
                                └─ <95% → 转人工清单（该类不自动应用）
                                应用后 → git commit + tag checkpoint
```

### 3.2 四类检查

| # | 检查 | 性质 | 方法 |
|---|---|---|---|
| 1 | 新闻稿分类 | 判断型（需抽样校） | heuristic 预筛 + LLM 逐条确认（见 3.3）|
| 2 | id-issuer 一致 | 确定性 | id 前缀(issuer_short) vs `issuer`/`issuer_canonical` 查 canonical 表，列不一致 + 提议正确 id |
| 3 | 去重再扫 | 判断型（重复组需抽样校）| 三维：URL 归一 + 文号归一 + 标题哈希；分组，提议留最早、其余迁 `_duplicates` |
| 4 | 残留 P_1900 | 确定性 | 列出（预期仅 1 篇山西 D 类）|

### 3.3 新闻稿分类器（唯一确定的设计选择：heuristic 预筛 + LLM 确认）

- **heuristic 预筛**（复用 `l1_collect/news_filter.py` 特征）：标题尾部"_市县"标签、域名特征（国际储能网 / 信用XX / 媒介转载域名）、source/issuer 非政府机构等 → 产出 candidate flags。安全通过的明显政策不进 LLM。
- **LLM 逐条确认**（temperature 0）：对每个 heuristic-flagged candidate，读「标题 + 正文开头」判定：
  - 输出 schema：`{pid, label ∈ {policy, news_release, index_page, reprint_only}, confidence, evidence}`
  - 只有 `label != policy` 且 confidence 达标的才进 proposed archive 清单
- 选型理由：无限算力下 LLM 逐条确认精度最高，够格自动归档；纯 heuristic 精度可能不到 95%，纯 LLM 扫全 999 最贵且对明显政策冗余。

### 3.4 抽样校验 + 阈值

- 对**判断型**输出（新闻稿 flagged、重复组）各抽样（≤50 条全抽，>50 抽 50，固定 seed 可重现）人工/LLM 校验精度。
- **≥95%** → 该类自动应用；**<95%** → 写人工清单 `state/source_ready/manual_review_<class>.jsonl`，该类**不**自动应用，其余达标类照常应用。
- 确定性检查（id / P_1900）无需抽样，按规则直接应用。

### 3.5 应用动作（全部可逆）

| 处置 | 动作 | 可逆性 |
|---|---|---|
| 确认新闻稿 | `git mv` → `0_raw/_archive/policies/news_release_<date>/` + 写 archive log | ✓ 可逆 |
| 重复 | `git mv` → `0_raw/_duplicates/` + 写 dedup 字段（`_duplicate_of` 等，见 SCHEMA §2）| ✓ 可逆 |
| id-issuer 不一致 | **就地重算** id/issuer/issuer_canonical，按 SCHEMA §C 白名单：aliases 保留旧 id、记 `<field>_fixed_at/_method/_from` | 审计字段留痕 |
| 残留 P_1900 | 不动，进 backlog（1 篇山西）| — |

**关键**：id 就地重算后**不**触发派生层 remap（派生层将在 ③整体重建）。这避免了历史上"修 id → 搬老边 → 掉一地迁移废料"的循环。

### 3.6 Checkpoint

- 应用完成 → vault `git commit` + `git tag clean-L1-<date>`
- 写 `state/source_ready/STATUS.md`：审计前后政策数、各类处置数、抽样精度、残留 backlog

## 4. 子项 b · 词表校验

- 扫 `_meta/themes_registry.yaml` + `1_extracted/entities/registry.yaml`：重复 id、冲突 alias、孤儿条目
- 产出报告 `state/source_ready/vocab_check.md`；轻量冲突手工修或提议
- 注：每篇政策"能挂的 theme 是否在表内"属 ②归属 的工作，这里只保证 registry 自身干净 + 完整

## 5. 子项 c · 框架结构化

把现散落在 vault `00 背景资料/` 的框架，收成 agent 可直接 load 的结构化文件（source 层资产）。落点建议 `_meta/framework/`：

| 文件 | 来源 | 内容 |
|---|---|---|
| `scoring.yaml` | 政策重要性打分体系 | 六维 D1–D6 + 重要性公式 + 行动分类 A/B/C/D |
| `decision_framework.yaml` | 滴滴能源背景 | 四维（要不要做/怎么做/何时做/风险）+ 三业务关注点 |
| `factcheck_rules.yaml` | 月报原型 §5 | 比较级核查、国家级→省级 6-12 月起草周期/同月不画因果、linkage 修辞防御 |
| `report_blueprint.yaml` | 月报原型 §3/§4 | 月报章节蓝图 + 业务表述规范（三大业务+乡村）+ 禁用项 |
| `index.yaml` | — | 索引以上 4 个文件，供 agent 一次性 load |

- 格式：可枚举的规则/配置用 YAML；叙事型指引可用 MD/prompt 模板
- gate：4 个框架文件 + index 存在且合法

## 6. 数据流 / 文件落点

| 物 | 落点 | 仓 |
|---|---|---|
| 审计脚本（可复用，非 oneshot）| `scripts/l1_audit/` | pipeline |
| dry-run 报告 / proposed_changes / 抽样日志 / 人工清单 | `state/source_ready/` | pipeline（过程产物，不进 vault）|
| 归档移动、id 修正 | `0_raw/_archive/`、`0_raw/_duplicates/`、raw frontmatter | vault |
| 框架结构化文件 | `_meta/framework/` | vault（source 资产）|
| checkpoint tag | `clean-L1-<date>` | vault git |

## 7. 错误处理 / 兜底

- LLM 分类失败/超时 → 标 unresolved，排除出自动应用，进人工清单
- 抽样精度 <95% → 该类不自动应用，写人工清单，其余类照常；流程不中断
- 一切移除都是 `git mv` 到 `_archive`/`_duplicates`，**不删除**，可恢复
- **幂等**：dry-run 对已干净语料 → 空 proposed_changes；apply 重跑 → no-op（已归档的不再动）

## 8. 测试策略（TDD）

- **单元**：news_filter heuristic 特征抽取（fixtures：已知新闻稿标题 vs 政策标题）；id-issuer 一致性解析（fixtures：已知错标如 GO/广州市商务局）；三维去重归一化 + 分组
- **契约**：LLM 分类器 prompt 返回合法 schema（测试用 mock LLM）
- **集成**：dry-run 跑一个小 fixture 语料（如 10 篇含 2 篇植入新闻稿 + 1 组重复）→ 预期 proposed_changes；apply → 预期归档移动；重跑验证幂等

## 9. 不做（YAGNI）

- 不建关系/业务/结晶（②③）；不建 index/API/L3（④）
- 不 remap 派生层（③整体重建）
- 不重抓 raw
- 不在本节点做"每篇政策→theme 挂载"（那是 ②）

## 10. 与 charter / SCHEMA 的衔接

- 归档/去重/id 重算全部落在 SCHEMA §C 白名单 + §D 重抓重入 + §2 已有约定内，不扩 schema
- 本节点产出的"干净 L1 checkpoint" = ②③ 的输入冻结点
- 框架结构化文件 = ④ 消费层 LLM 按需合成时 load 的规则源
