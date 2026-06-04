# ③分析层整体设计

## 1. 定位

③分析层不是 `signal_context` 本身。它是四层重构里的跨篇分析层,承接 ②归属,输出给 ④消费。

③包含两条线:

1. **政策关系主线**:政策与政策之间的引用、依据、废止、迭代、细化、落地、扩展、对齐。
2. **三源信号辅线**:已闭环的评论信号和市场验证信号被聚合成内部 `signal_context`。

两条线在③汇合,形成 ④可读取的分析上下文。④默认展示政策依据、业务判断和不确定性提示;不默认展示评论/市场信号原始证据。

## 2. 当前事实

- SCHEMA 已定义 `1_extracted/relations/<rel>.jsonl` 的 9 类关系。
- Vault 已有旧 `1_extracted/relations/` 文件,包括 `derives_from`、`references`、`cites_basis`、`aligns_with`、`clarifies`、`extends`、`iterates`、`supersedes`。
- 旧关系产物是 stale:产于 raw 清洗、②-A 改身份、②-B 挂主题之前。
- 当前工程仓没有可复用的 `scripts/l2_derive` 抽取器,只有 `.gitkeep`。
- `derived_signals` 已纠偏:已发布评论信号 171 条、市场信号 10 条;31 条待人工闭环信号被拦截,不得进入下游。
- Vault 当前有一个未跟踪 raw 政策文件。③实现前必须先处理或明确隔离,否则不能声称输入语料冻结。

## 3. 目标

③要回答:

- 哪些政策引用、依据、细化、迭代或废止了哪些政策?
- 国家政策如何被省市落地或扩展?
- 哪些主题和区域形成了政策簇,哪些仍是孤岛?
- 哪些政策判断受到评论关注、风险或执行阻力提示?
- 哪些主题/区域已有市场验证信号?
- 哪些地方需要降低确定性、提高关注或进入人工复核?

③不产出最终报告。③生成可审计、可复现、可由 ④读取的分析上下文。

## 4. 非目标

③不做:

- 不改 `0_raw/`
- 不改 ② 的 policy theme 归属
- 不改 `_meta/business_view/*.yaml` 分数
- 不消费 review queue
- 不把 blocked signals 当已确认数据
- 不复用旧 relations 作为可信事实直接发布
- 不生成最终 ④ 报告或卡片

## 5. ③的输入

可信输入:

- `0_raw/policies/*.md` 的只读 frontmatter/body
- `_meta/business_view/*.yaml` 的新流程产物
- `1_extracted/commentary_signals.jsonl`
- `1_extracted/market_intel_signals.jsonl`
- `_meta/themes_registry.yaml`
- ②-A 身份归属台账和当前 raw aliases

不可信或限制输入:

- 旧 `1_extracted/relations/*.jsonl`:只能做审计对照和候选提示,不能直接当新③事实发布。
- `state/derived_signals/*/blocked_signals.jsonl`:只能用于报告“被排除”,不能作为 accepted 输入。
- 旧 business_view backup:不能参与运行时分析。
- legacy archive:不读。

## 6. ③的输出

第一阶段只做 preview:

- `state/analysis_layer/preview_YYYYMMDD/relation_inventory.json`
- `state/analysis_layer/preview_YYYYMMDD/policy_relation_candidates/*.jsonl`
- `state/analysis_layer/preview_YYYYMMDD/signal_context/*.jsonl`
- `state/analysis_layer/preview_YYYYMMDD/analysis_context/*.jsonl`
- `state/analysis_layer/preview_YYYYMMDD/reports/analysis_layer_preview.html`

后续 apply 若获批准,可以写:

- `1_extracted/relations/*.jsonl`
- `1_extracted/relations/_index_by_policy/*.md`
- `1_extracted/signal_context/*.jsonl`
- `1_extracted/analysis_context/*.jsonl`

Apply 必须只消费 preview 输出,整文件写入派生层。

## 7. 模块拆分

### ③-A 关系资产审计

先不重生关系,先盘点旧关系:

- 每类关系数量
- `from/to` 是否仍能在当前 raw id 或 aliases 中定位
- 是否含 P_1900、重复索引、archive 边、旧 extracted_by
- 哪些关系类型历史精度高,哪些历史精度低

输出:关系资产可信度报告。

### ③-B 高精度政策关系 preview

先处理高确定性的关系:

- `references`:正文显式文号引用
- `cites_basis`:开头/依据段“根据/依据/落实”语义
- `supersedes`:显式废止、同时废止、替代
- `clarifies`:标题和正文明确“实施细则/解读/操作指引”

这部分可以早于 ②-B 全量完成做 preview,因为它主要依赖 raw 正文、文号和 id/aliases。

### ③-C 语义政策关系 preview

再处理更依赖 ②归属质量的关系:

- `derives_from`:国家到省市落地
- `extends`:范围扩展或试点扩围
- `aligns_with`:不同部门/地区同主题对齐
- `iterates`:同机构同主题年度续作或版本迭代
- `conflicts_with`:中国政策语境中罕见,默认谨慎,更多应通过评论分歧观察

这部分必须依赖稳定 theme/region/business_view,因此应在 ②-B 全量或足够覆盖后再 apply。

### ③-D signal_context

读取已发布的:

- `commentary_signals.jsonl`
- `market_intel_signals.jsonl`

输出:

- policy context
- theme context
- region context

它与政策关系主线并列,不是替代政策关系。

### ③-E analysis_context

把政策关系主线和 signal_context 合成 ④可读取的统一上下文:

```json
{
  "policy_id": "P_xxx",
  "relation_summary": {
    "basis_count": 2,
    "superseded_by_count": 0,
    "derives_from_count": 1
  },
  "signal_summary": {
    "commentary_attention": "medium",
    "market_validation": "weak"
  },
  "analysis_flags": ["has_basis_chain", "market_validation_weak"],
  "audit_refs": {
    "relation_ids": ["R_xxx"],
    "commentary_ids": ["C_xxx"],
    "market_signal_ids": ["MI_xxx"]
  }
}
```

④默认读 `analysis_context`,而不是直接读 raw relations 或 raw signals。

## 8. 推荐先后顺序

推荐顺序:

1. **③整体设计确认**:当前步骤。
2. **③-A 关系资产审计 preview**:只读旧 relations 和当前 raw,出 HTML。
3. **③-B 高精度关系 preview**:先做 references / cites_basis / supersedes / clarifies。
4. **signal_context preview**:可以与 ③-B 并行或紧随其后,因为已发布 signals 已闭环。
5. **analysis_context v1 preview**:只把 ③-B 与 signal_context 合成临时统一输入,用于验证上下文契约;这不代表③关系层完成,也不代表④可以开始实质消费。
6. **③-C 语义关系机制确认**:先明确 `derives_from`、`extends`、`aligns_with`、`iterates` 等语义关系怎么生成、怎么过模型/程序门、怎么进入人工池。
7. **等 ②-B 覆盖足够后做 ③-C 语义关系 preview**。
8. **analysis_context v2 preview**:纳入③-C accepted 语义关系后,再作为④实质消费层输入。
9. **所有 apply 另行批准**。

不推荐现在直接实现完整 ③-C,因为 ②-B 覆盖只有 50 个 business_view,语义关系会重复旧关系的问题。

④可以先做读取契约说明,但不应在③-C和 analysis_context v2 之前启动政策卡片、报告或其他实质消费 preview。

## 9. 与 signal_context 的关系

`signal_context` 是③的一条辅线。它可以先做 preview,但不能被误认为③完成。

正确关系:

- 政策关系主线回答“政策之间如何连接”。
- `signal_context` 回答“评论/市场信号如何调整注意力和确定性”。
- `analysis_context` 把两者合并成④输入。

## 10. ④读取约束

④默认读取:

- `analysis_context`
- 必要时读取 `policy_context`、`theme_context`、`region_context`

④默认不读取:

- raw commentary titles
- raw market intel titles
- signal evidence snippets
- blocked signals
- old relations as accepted facts

审计模式才展开:

- relation evidence
- signal evidence
- confidence
- `sanitized_from`

## 11. 验收门

③ preview 必须证明:

- 不写 raw
- 不消费 review queue
- 不读取 blocked signals 当 accepted
- 不把旧 relations 直接发布为新事实
- 所有关系 `from/to` 可由当前 raw id 或 aliases 定位
- P_1900、重复索引、archive 关系进入审计提示,不能静默发布
- 高精度关系和语义关系分开统计
- HTML 报告使用中文,清楚标注哪些是 preview、哪些是待人工/待②-B
- 凡接入模型的 ③/④ 子流程,必须能用普通模型(MiniMax/DeepSeek 等)按硬化 prompt 跑;正确性由确定性闸门、schema 校验、审计门和人工池阻断兜底,不能依赖强模型自由发挥

## 12. 模型使用约束

③-A 关系资产审计不调用模型。

后续 ③-B/③-C/③-D/④ 如果需要模型,模型只负责受限判断或结构化抽取,并必须满足:

- prompt 是全局硬化规则,不是 PID 或 case-by-case 补丁。
- 普通模型可接入:MiniMax/DeepSeek 等模型输出必须经过相同 schema、program gate、审计报告和人工池。
- 高精度关系优先用确定性证据(文号、显式引用、废止语句)。
- 语义关系要依赖②归属结果和回归样本;不确定时进人工池,不能继续往下塞。
- 人工池结论回流到流水线,不能绕过 preview/apply。

## 13. 当前要做的第一件事

下一步不是实现 `signal_context`。

下一步应做 **③-A 关系资产审计 preview**:

- 只读 vault 旧 `1_extracted/relations/`
- 只读当前 `0_raw/policies`
- 解析当前 id/aliases
- 给每条旧关系标记:可定位 / id 漂移 / P_1900 / archive / 低可信类型 / 可作为候选
- 输出中文 HTML 和机器 JSON

这样先把政策主线的地基摸清,再决定哪些关系可重生、哪些必须丢弃或重新抽取。
