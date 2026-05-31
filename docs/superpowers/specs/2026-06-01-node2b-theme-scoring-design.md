# ②-B 归属挂载(theme + 重要性打分)— 设计 spec

- **日期**:2026-06-01
- **状态**:设计已与用户分段确认,3 决策全锁定,待写 plan
- **定位**:加工(L2)里的「归属」子阶段(承 ②-A 确定性身份;不碰 ③分析/L3取)
- **前置**:②-A 确定性身份固化已完成(148 篇,vault tag `pre-2a-2026-05-31`)
- **审计基线**:源文档审计 `docs/audits/2026-05-31-source-doc-audit-*.html`(八步采集法/L2建设思路 已贴标记冻结,本 spec 不依赖二者)

---

## 1. 定位与边界

**做什么**:一次 per-policy 的 LLM pass,给 vault 现有 **935 篇政策**每篇:
1. 挂 **theme(s)** — 命中的所有主题(不限数量)+ 1 个 **主 theme**
2. 打 **重要性分** — 六维 D1–D6 + 脚本算综合分/行动分类/价值标签
3. (过门的)写 **3-key 影响分析 + 行动建议**

产物:**整文件重生** `_meta/business_view/{pid}.yaml`(加 `themes` / `primary_theme` 字段)。

**不做**(明确划界,防旧 L2 黑箱回潮):
- ❌ 关系网抽取(supersedes/references/derives_from…)= **③分析**
- ❌ 主题聚合页 / 区域页 / 反链页 / 渲染 = **L3取 / 结晶**(③/④)
- ❌ 任何写 raw frontmatter / body 的动作(见 §下纪律)

**为什么是一个节点**:theme 挂载与重要性打分都是"读这一篇、判断它本身"的 per-policy 归属判断,天然合一,一次 LLM pass 出。跨篇(关系)、聚合(结晶)才是后面的节点。

---

## 2. 三个已锁决策(用户 2026-06-01 确认)

| # | 决策 | 选定 | 理由 |
|---|---|---|---|
| 1 | 一篇挂几 theme | **不限数量 + 1 主 theme** | 国家级规划纲领必然多主题,设上限会在最高价值政策上翻车 |
| 2 | 打分深度 | **两遍 + 确定性门 = 重要性≥3 OR 国/省级** | 分层为信噪比(非省钱):对零相关政策强写影响分析=逼模型幻觉 |
| 3 | judge 校准 golden | **约50篇分层 · 我(Opus4.8)写gold+塞拟真错 · 用户抽查~10 · 冻结** | 整条链信任锚在答案键,人工抽查是低成本兜底 |

---

## 3. 权威输入 / 非权威

**权威(spec 唯一依据)**:
- `_meta/themes_registry.yaml` — 13 主题 canonical 词表 + aliases(注:在 `_meta/`,非 `_meta/framework/`)
- `_meta/framework/scoring.yaml` — 六维 D1–D6 + `重要性=round(D1·.4+D2·.4+D3·.2)` + 行动分类(D4×D5 2×2 + D6修正)+ 价值标签
- `_meta/framework/decision_framework.yaml` — 3 业务(加油/充电/电力)+ 决策层口径
- `SCHEMA.md` §4(business_view 契约)+ §C(raw 边界)
- 四节点 / 统一结构约定(见 MEMORY 结构约定)

**非权威**:
- ⛔ `report_blueprint.yaml` / `factcheck_rules.yaml` — TAINTED(归 L3 呈现规范)
- ⛔ 「L2建设思路」整篇 — 旧模型(其三洞察归 ③)
- 八步采集法 Step 5C — **只作 business_view schema 形状参考,非方法**

---

## 4. 数据模型(business_view schema)

沿用 SCHEMA §4,**新增 theme 两字段**:

```yaml
pid: P_2024_NDRC_718
# === 归属:theme(②-B 新增) ===
themes: [energy_storage_theme, power_market, vpp_theme]   # 命中的全部,∈ themes_registry
primary_theme: energy_storage_theme                       # 1 个主 theme,∈ themes
# === 评分(必填) ===
scores: {D1: 5, D2: 4, D3: 4, D4: 4, D5: 4, D6: 5}
重要性: 4                       # 脚本 = round(.4D1+.4D2+.2D3)
行动分类: A                     # 脚本 = D4×D5 2×2 + D6修正
价值标签: [合规, 机会]          # 脚本 = 综合分 + theme 推导
# === 深档(可选,过门才写;门 = 重要性≥3 OR 国/省级) ===
影响分析:                       # 3-key,固定这三个键
  加油: "..."
  充电: "..."
  电力_储能_V2G_交易: "..."
行动建议: ["A 趁早:...", "B 研究:..."]   # 注:用"趁早"非"立即"
didi_impact_one_liner: "..."    # 可选
# === 可追溯(必填) ===
sanitized_from: 0_raw/policies/{filename}.md
extracted_at: '2026-06-01'
extracted_by: scripts/l2_themescore/run_2b.py
extracted_model: <model A id>
gate_passed_deep: true          # 是否过深档门(可审计)
archive: ~                      # 综合分<3 时填 low_score
```

**themes 落派生层、不落 raw**(§C 关键判定):theme 是 **LLM 语义标签**,§C 明令"语义标签"不写 raw → 只进 business_view。顺带消除旧版 `tags` 倒灌 raw 的污染(SCHEMA §F 登记的 81 篇违规)。③/④ 建主题聚合页时读 `business_view.themes`,不靠 Obsidian 反链。

---

## 5. 架构与数据流

```
935 raw policies (复用 ②-A corpus 加载器)
        │
        ▼  遍1:generator(模型A,temp0)
  themes[] + primary_theme + D1–D6        ← prompt 由 themes_registry + scoring 构建
        │
        ▼  确定性计算(脚本,无 LLM)
  重要性 / 行动分类 / 价值标签 / gate判定
        │
        ├─ 过门(重要性≥3 OR 国省级)─▶ 遍2:generator(模型A)
        │                              3-key 影响分析 + 行动建议
        │                                       │
        ▼◀─────────────────────────────────────┘
  完整 business_view 候选(未落盘)
        │
        ▼  两层验收门
  ┌─ 程序门(§7,纯函数,先跑)
  └─ LLM judge(模型B≠A,§8,语义)
        │
        ├─ 双门通过 ─▶ 整文件重生 _meta/business_view/{pid}.yaml
        └─ 任一否 ───▶ review_queue(低置信)+ 报告
```

**模型分工**:
- **模型 A**(便宜,用户提供)= generator,跑两遍。`scripts/common/llm.py`,temp0。
- **模型 B**(≠A,用户提供)= judge。
- **我(Opus4.8)**= 测试期出题/校准 + 门失败重调;上岗后例行不参与(B6.1)。

**D1 判断 vs 影响分析输出的口径**:D1 业务关联度按 scoring.yaml 的 **4 业务版块**(加油/充电/储能VPP/电力交易,core_premise:充电站=电力市场参与者)判;**影响分析输出固定 3 key**(加油/充电/电力_储能_V2G_交易),后两版块并入"电力"。

---

## 6. 确定性计算(纯函数,不依赖 LLM)

全部可单测、可重算自洽(程序门据此重算校验):
1. `重要性 = round(D1·0.40 + D2·0.40 + D3·0.20)`(范围 0–5)
2. `行动分类`:D4(紧迫)×D5(实操)2×2 → A立即/B优先研究/C计划跟进/D持续跟踪;再用 D6 机会窗口修正(5–4 前跳一档、2–1 后降一档)
3. `价值标签` ⊆ {合规, 机会, 壁垒, 趋势}:综合分 + theme 组合推导(规则化)
4. `gate_passed_deep = (重要性 ≥ 3) OR (region.level ∈ {国家, 省})`
   - region.level 取自 raw(②-A 已确定性固化),不重新判

---

## 7. 程序门(第一层,纯函数,先于 judge)

任一不过 → 不写派生层,入队:
- **结构**:必填字段齐;`themes` 非空;`primary_theme ∈ themes`
- **公式自洽**:用 D1–D6 重算 重要性/行动分类,与 LLM 自报一致(LLM 只报维度,综合分以脚本为准)
- **registry 合规**:`themes ⊆ themes_registry.id`(每个 theme 都在 13 主题内)
- **影响分析键(正向白名单)**:过门篇的键 = 恰好这三个,多一个或少一个都拒——任何 stray 键自动挡掉,不点名任何具体词
- **深档⟺门**:`(影响分析非空 且 行动建议非空) ⟺ gate_passed_deep`
- **分布合理**:全量统计——不允许"每篇都挂满 13 theme"(过挂信号);theme 分布、重要性分布、孤岛(0 theme)数落报告

---

## 8. LLM judge + golden 校准

**judge 职责**:程序门管不了的**语义质量** —— theme 挂对没(漏挂/错挂)、分数合不合理、影响分析有没有幻觉(对零相关政策硬写)/ 该写没写。输出 `{verdict: accept|reject, dim: theme|score|impact, reason, confidence}`。

**golden 集(测试期一次性)**:
1. 从 935 **分层抽 ~50 篇**:覆盖 13 theme × 国/省/市级 × 高/中/低重要性 × 过门/不过门
2. 我(Opus4.8)写每篇 **gold 标注**(themes+primary+D1–D6+影响分析)
3. 注入**拟真错**(模仿模型A真实错法):乱挂热门theme / 漏挂主题 / 低估地方政策分 / 幻觉业务影响 / 影响分析键缺失。每错型若干,记 `error_type` 与 `is_planted`
4. **用户抽查 ~10 篇** gold(答案键人工兜底一道)
5. **冻结** → `state/node2b/golden/golden_v1.jsonl`(committed,immutable)

**judge 上岗门**:judge 跑 golden,测
- **召回** = 抓住的埋错 / 总埋错(别漏)
- **精度** = 判错里真错 / 判错总数(别冤枉对的)
- 阈值在上岗那刻看实测分布定(测试期我裁决);达标才放 judge 例行 4.8-free

**上岗后**:generator→程序门→judge 全自动;我只在**门失败重调**或**定期审低置信队列**(接 B7)回来。

---

## 9. theme 词表 + B5 收口(②-B 顺带做)

B5「词表 4 处不自洽」明确推后到"②建主题匹配时定",本节定:
1. **`负荷聚合` 同时在 vpp_theme + aggregator_access** → **两个 theme 都保留**(用户 2026-06-01 定)。与决策1(多theme)一致:提到"负荷聚合"的政策对两主题都是候选,语义 LLM 定实际挂哪(可能都挂)。**B5 规则随之改**:alias 允许跨 theme 共享、不再当冲突,vocab lint 放行共享 alias。
2. **`成品油零售` 归属** → 留 petroleum_retail_compliance(合规向);gas_station_transition 是"油站物理转型",不拥有该词。entities 若有重复,以此为准。
3. **charging_infra / power_market / v2g 的 entity 补 `type=theme`**(themes_registry 已有,entities/registry 缺 type)——机械补齐。
4. **删 stale theme entity(一次性)**:entities/registry 里那个早被 B9 判"非 theme"的 `rural_revitalization_theme` 残留(已不在 13 主题词表、正向规则下永不可挂)→ B5 顺手删其 type=theme,纯属清死数据;非 ②-B 正确性依赖。
- 以上是**对源资产(词表)的确定性整理**,走 append+review,记入 spec;非补丁。

> ✅ §9.1 已定(2026-06-01):两个 theme 都保留;由此确立"**alias 可跨 theme 共享**"为词表通则(§9.2 成品油零售 经判断不属共享,仍单归 petroleum_retail_compliance)。

---

## 10. SCHEMA §4 门校准(合法 schema 演进)

SCHEMA.md §4 现写「影响分析/行动建议(可选,**D1≥3** 时填)」。
→ 改为「(可选,**重要性≥3 OR region.level∈{国家,省}** 时填)」。
新增 `themes` / `primary_theme` / `gate_passed_deep` 字段定义。
**走 SCHEMA 修改流程,留评审记录**(SCHEMA 自身规则:不允许约定俗成扩张)。这是演进非补丁。

---

## 11. 模块结构(新 `scripts/l2_themescore/`,复用 ②-A 基建)

```
scripts/
├── common/llm.py                 (已有,复用 — temp0 客户端)
├── l2_attribution/               (②-A,复用其 corpus 加载器 / models 基类)
└── l2_themescore/                (②-B 新建)
    ├── models.py                 ThemeAssignment / Scores / BusinessViewDraft / GoldenRecord / JudgeVerdict
    ├── theme_registry.py         load themes_registry + alias→id lookup + validate
    ├── generator.py              模型A:遍1(theme+分)/ 遍2(影响+建议);prompt 构建
    ├── scoring.py                确定性:重要性/行动分类/价值标签/gate(纯函数)
    ├── program_gate.py           §7 程序门(纯函数)
    ├── judge.py                  模型B 客户端 + verdict 解析
    ├── golden.py                 golden 加载 + judge 跑分(召回/精度)
    ├── business_view_writer.py   整文件重生 business_view/{pid}.yaml(§C 安全:绝不碰 raw)
    ├── review_queue.py           低置信入队
    ├── report.py                 HTML 报告(分布/门结果/队列)
    └── run_2b.py                 编排 CLI:dry-run / apply / verify
tests/l2_themescore/             单元(scoring/gate)+ golden(judge)+ 集成(dry-run 样本)
state/node2b/
    ├── golden/golden_v1.jsonl    冻结答案键
    ├── proposed_changes/         dry-run 产物
    └── review_queue/
```

---

## 12. 错误处理 / 队列

| 情况 | 处理 |
|---|---|
| 模型A 返回非结构化 JSON | 重试 1 次 → 仍失败标 `generation_error` 入队 |
| 程序门失败 | 不写派生层,入 `review_queue`,报告归类 |
| judge reject | 入低置信队列;测试期我审,上岗后批量回 generator 重生 |
| business_view 已存在(②-A改id化石 / 旧字段残留) | **整文件重生覆盖**(by 当前 raw id),不 patch |
| LLM 多次评分不一致 | 取中位数 + `_dispute` 字段(沿用 SCHEMA §4) |

**顺带清理**(随整文件重生自动,by construction):整文件重生用正向 3-key 规则重写,旧文件里任何 stale 键(含历史遗留)一并消失,无需点名。

---

## 13. 测试策略

- **单元**(纯函数,必全绿):scoring(重要性/行动分类/价值标签/gate 边界)、program_gate 每条规则、theme alias lookup
- **golden**:judge 跑冻结 golden,产召回/精度报告
- **集成**:dry-run on ~30 篇样本,验证两遍流程 + 双门 + 写出格式
- **零回归**:business_view 重生后跑 SCHEMA validator(0 违反)+ ledger 一致性(若涉及)

---

## 14. 纪律 / 滑坡自审(每步收尾必跑)

- **常驻规则非快照**:theme 法、门、阈值都是规则;golden 是冻结基准(钉快照但显式冻结、可复现)
- **零 pid 硬编码**:generator/gate/scoring 无任何针对具体 pid 的分支
- **动视图非源**:只写 `_meta/business_view/`(派生层);**raw 一字不动**;themes 是语义标签 → §C 禁入 raw
- **不漏**:所有 LLM 判定(theme/分/影响)全落派生层;确定性算分在脚本
- **零补丁**:改框架/词表 → 整文件重生;不写针对 ②-B 输出的 oneshot/migration(charter 违约信号)

---

## 15. 交付物清单 + 验收门

**交付物**:
1. `scripts/l2_themescore/` 全模块 + 测试
2. golden_v1.jsonl(我标 + 用户抽查 + 冻结)
3. judge 校准报告(召回/精度)+ 上岗阈值
4. dry-run 报告(935 篇 theme/分/门结果分布)
5. SCHEMA §4 校准(改门 + 加字段 + 评审记录)
6. themes_registry / entities B5 收口(§9)

**人工验收门(停)**:
- A:judge 校准达标(召回/精度)→ 我裁决放行
- B:935 dry-run 报告 → 用户看分布(theme 合理?孤岛多少?过门比例?)→ 批准
- C:apply 写 business_view(派生层,非 raw,风险低)+ verify 幂等
- 一次性迁移验证(非常驻规则):全量重生后 grep 确认历史 `乡村` 残留键 = 0,作为 B9 去污染收尾证据;此后"乡村"不出现在任何常驻逻辑里

---

## 16. 开放/待定项(写 plan 前)

1. ~~§9.1~~ ✅ **已定(2026-06-01)**:`负荷聚合` 两个 theme 都进;确立 alias 可跨 theme 共享(见 §9)
2. **A/B 两个三方模型**:用户寻找中(spec 不依赖具体选型,模型是配置项)
3. **judge 达标阈值**:上岗那刻看实测定(不预设)
4. **golden 分层抽样的精确配额**:写 plan 时定(保证 13 theme 均有样本)
