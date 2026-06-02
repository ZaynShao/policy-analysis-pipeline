# 政策情报四层重构 · 三源接入设计

## 1. 命名与定位

本工程命名为 **政策情报四层重构**。

它不是单纯的政策文本处理 pipeline,而是一套把三类素材转化为可审计、可复现、可消费的决策情报系统:

- **政策**:政府正式文件,回答"规则是什么"。
- **评论**:媒体、公众号、行业机构、专家解读,回答"外部如何理解、争议在哪里、市场预期是什么"。
- **市场情报**:项目清单、招标、补贴、并网、容量、价格、公示等地面信号,回答"哪里已经出现业务机会或执行动作"。

四层结构为:

1. **源到位**:三源进入各自 raw / state 边界,事实与来源可追溯。
2. **归属**:把素材归到政策、主题、地区、业务线、观点/机会类型。
3. **分析**:把单篇判断连接成关系、评论校准信号、区域差异、市场信号验证。
4. **消费**:生成报告、决策卡片、主题页、区域视图、查询接口。

## 2. 核心评估

现状的 schema 已承认评论,并为评论 raw、评论审计、评论观点产物预留了位置;backlog 也承认 market_intel 第三源。但已落地的 ②-A / ②-B 主线实际上主要围绕政策本体推进。尤其 ②-B 的 `business_view` 只消费 `0_raw/policies`,没有把评论作为校准信号输入,也没有把市场情报作为验证信号输入。

这不是原则崩塌,但它暴露了一个结构性风险:如果继续只推进 `business_view` 全量重生,系统会变成"政策本体归档与评分系统",而不是"政策情报系统"。对决策层来说,后者才是目标。

## 3. 三源角色边界

### 政策

政策是事实锚点。政策主题、分数、影响分析进入 `_meta/business_view/{pid}.yaml`。政策之间的演进、引用、废止、落地关系进入 `1_extracted/relations/`。

政策不应被评论直接改写。评论可以挑战政策解读,但不能覆盖政策原文事实或单篇政策的正式归属。

### 评论

评论是校准层,不是事实源,也不是消费层默认外显的"观点证据"。它的价值在于:

- 识别市场共识与分歧。
- 解释政策为什么重要或为什么被忽视。
- 暴露行业担忧、执行阻力、套利空间、口径变化。
- 作为内部参数校正政策重要性、可执行性和风险判断。

评论应在 ② 归属阶段生成最小工程字段,进入 `1_extracted/commentary_signals.jsonl`:

```yaml
commentary_id: C_xxx
related_policy_ids: [P_xxx]
theme_ids: [charging_infra, v2g]
signal_role: opportunity|risk|execution|attention|interpretation|noise
confidence: 0.0-1.0
evidence: 原文短摘或位置
```

这些字段只保留有工程消费者的内容:`related_policy_ids` 用于挂回政策,`theme_ids` 用于主题聚合,`signal_role` 用于内部校准,`confidence` 用于聚合加权,`evidence` 用于审计追溯。

评论不应直接写入 `business_view` 的 `scores` 或 `themes`,否则会把外部观点和政策本体混在一起。

### 市场情报

市场情报是执行信号,不是政策也不是评论。它的价值在于验证政策是否正在落地,以及哪里出现可执行机会。

市场情报应有独立 representation,不能简单塞进 commentaries 或 policies。短期可保留 manifest / audit 标记,不丢弃;中期需要定义结构化字段:地区、项目类型、金额/容量/指标、时间戳、来源、关联主题、关联政策。

## 4. 四层接线

### ① 源到位

目标不是只有政策清洗干净,而是三源边界清楚:

- `0_raw/policies`:正式政策。
- `0_raw/commentaries`:评论/解读/分析。
- `market_intel`:先以 manifest 或 state 承认,待 schema 成熟后落正式 raw 或时序结构。

done-gate 应包括三源数量、未分类素材、误入 policies 的 commentary、误入 policies 的 market_intel。

### ② 归属

政策归属包括 issuer / region / date / theme / importance / business_view。

评论归属包括 commentary_id / related_policy_ids / theme_ids / signal_role / confidence / evidence。

市场情报归属包括 region / theme / opportunity_type / business_line / time_validity / related_policy。

② 的关键是各归各位,不是把三源揉成一个判断。

### ③ 分析

③ 不能只做政策关系。它应至少包含三类内部分析:

- 政策关系:废止、迭代、引用、派生、区域扩展。
- 评论信号:机会、风险、执行、关注度、解释性、噪声。
- 市场验证:招标/补贴/项目/容量/价格等信号对政策主题的验证。

这三类分析在 ③ 汇合,但仍保持来源类型和证据路径。

### ④ 消费

④ 面向决策层。消费层不应只展示"政策列表 + 分数",也不应把内部方法论外显成"因为注入了政策依据、外部观点、市场信号,所以得出结论"。正确口径是:对外输出结论、影响和建议;必要时外显政策依据。评论与市场信号默认作为内部校准/验证参数,只在用户追溯、质疑或审计时展开。

消费层应回答:

- 哪些主题正在升温?
- 哪些区域的机会判断更可靠?
- 哪些政策需要被提高或降低关注权重?
- 哪些机会政策依据强,但落地可信度不足?
- 哪些机会热度高,但正式政策依据薄弱?

## 5. 对当前 ②-B 的判断

②-B 已经完成了 policy-only 的重要机制:theme registry、scoring、program gate、judge、manual review pool、offline apply。这些是必要资产,不应推倒。

但 ②-B 不应被误认为"政策情报归属层已完成"。它只完成了政策本体归属的一部分。评论归属和市场情报归属还没有进入同等工程纪律。

下一步不建议直接全量重生 935 篇 business_view。更合理的顺序是:

1. 先补三源接线审计,明确三源在 ①/②/③/④ 的输入、产物和 done-gate。
2. 再决定 ②-B 全量 business_view 是否继续推进。
3. 同时定义 `commentary_signals` 最小闭环,避免 ③/④ 继续 policy-only。

## 6. 推荐路线

推荐采用 **顾问式重构路线**:

1. **一页总图**:政策情报四层重构的三源接线图。
2. **现状审计**:统计三源数量、现有产物、缺口、stale 资产。
3. **done-gate 重写**:为 ①/②/③/④ 加入 policy/commentary/market_intel 三源条件。
4. **最小闭环优先**:先让评论进入一个小范围 policy 的内部校准信号,再继续全量 business_view。
5. **业务消费倒推**:从决策问题倒推三源产物,避免继续堆派生文件。

## 7. 原则

- 不用评论改写政策本体。
- 不把市场情报混入政策或评论。
- 旧 `business_view` 不保留在可消费资料库中;最大妥协是库外 backup,不参与 pipeline。
- 不用 PID 补丁修视角问题;修三源边界、schema、done-gate 和消费契约。
- 所有展示性评估输出 HTML。
