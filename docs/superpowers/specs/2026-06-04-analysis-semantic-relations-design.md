# ③-C 语义政策关系生成机制设计

## 1. 这一步解决什么问题

③-C 解决的是“政策1 和 政策2 是否存在某类语义关系”的生成机制。它不是③-B那种文号命中即可成立的高精度关系,而是依赖②归属结果的跨篇判断。

本设计先定义机制和验收门,不立即生成语义关系。

## 2. 为什么不能现在直接跑

当前②-B只完成小规模新流程覆盖,还不足以支撑全量语义关系:

- `derives_from` 需要稳定的 theme、region 层级、issuer 层级。
- `aligns_with` 需要知道多篇政策是否属于同一主题簇。
- `extends` 需要知道前后政策的范围、地区、主题是否真的扩展。
- `iterates` 需要同机构、同主题、相邻时间或版本序列。

如果在②归属没有足够覆盖前全量跑③-C,会重演旧关系层的问题:先连线,后发现 identity/theme/region 变了,关系整体 stale。

## 3. 当前已经完成和没有完成的边界

已完成:

- ③-A:旧关系资产审计 preview。
- ③-B:高精度确定性关系 preview,只含 `references`、`cites_basis`、`supersedes`、`clarifies`。
- ③-D:`signal_context` preview。
- ③-E v1:把③-B和③-D合成临时 `analysis_context`。

未完成:

- ③-C语义关系 preview。
- ③-E v2,也就是纳入③-C后的 `analysis_context`。
- 写入 vault 的正式 `1_extracted/relations/*.jsonl`。
- ④实质消费层报告或卡片。

因此④目前只能做读取契约说明,不能开始真正业务消费。

## 4. 关系类型分层

### 4.1 可确定性优先的类型

`iterates`

- 判断含义:同一发文主体、同一主题、后续年份或版本对前一政策的延续/更新。
- 候选生成:同 issuer + 同 primary_theme + 标题相似 + 日期递增 + 标题含年度、试行、修订、办法、规则等版本信号。
- 接受条件:必须有可解释证据,不能只因标题像。
- 不确定时:进人工池。

`extends`

- 判断含义:试点范围、适用范围、区域范围或对象范围扩大。
- 候选生成:同主题或同政策链,后文含扩大、扩围、推广、全面实施、由试点转常态等范围信号。
- 接受条件:必须指出被扩展的对象和新范围。
- 不确定时:进人工池。

### 4.2 程序候选 + 受限模型判定的类型

`derives_from`

- 判断含义:地方或部门政策落实、承接、细化上级政策。
- 候选生成:
  - ③-B已有 `references` 或 `cites_basis` 指向上级政策。
  - from 政策 region/issuer 层级低于 to 政策。
  - 两者 theme 相同或高度相邻。
  - from 标题或正文有贯彻、落实、实施方案、实施意见、细则等承接信号。
- 模型作用:只判断候选证据是否支持“承接/落地”,不得自由寻找新关系。
- 不确定时:进人工池。

`aligns_with`

- 判断含义:不同地区、部门或机构在同一主题上形成政策方向对齐,但不声明因果依赖。
- 候选生成:
  - 同 primary_theme 或同主题组。
  - 发布时间相近。
  - 政策目标、工具或对象相近。
  - 不存在明确引用/依据关系时才考虑 `aligns_with`。
- 模型作用:只判断“是否足够相似到可形成政策簇”,不得把对齐说成依据或派生。
- 不确定时:默认不接受或进人工池。

### 4.3 默认不自动生成的类型

`conflicts_with`

- 中国政策语境下,政策正文之间很少明示冲突。大多数“冲突”更可能是执行口径、市场反馈、评论争议或过期状态造成。
- 默认不由③-C自动生成 accepted 关系。
- 只允许作为人工池或审计提示出现。
- 评论信号可以提示关注,但不能直接变成政策间冲突关系。

## 5. 生成机制

③-C必须拆成四层,不能让模型直接全库自由连线。

1. **候选生成**
   - 输入当前②归属结果、③-B高精度候选、policy metadata、标题、正文证据窗口。
   - 输出 `semantic_relation_candidates.jsonl`。
   - 候选只说明“可能存在关系”,不等于 accepted。

2. **受限判定**
   - 普通模型可接入:MiniMax/DeepSeek 等必须能按同一 prompt 输出同一 schema。
   - 输入只给候选双方、关系类型、证据窗口、②归属摘要和禁止事项。
   - 输出只能是 `accept`、`reject`、`manual_review`。

3. **程序门**
   - schema 不合法直接失败。
   - 缺 `from/to/rel/evidence/reason` 直接失败。
   - 关系类型不在白名单直接失败。
   - 证据窗口不支持关系则不能 accepted。
   - `manual_review` 不得进入下游 accepted。

4. **人工池**
   - 全局规则无法判断的进入人工池。
   - 人工裁决记录“放哪类/多类/保持待办”和理由。
   - 裁决回到正常 dry-run/apply,不能写源码 PID 特例。

## 6. ③-C 的数据契约

候选行:

```json
{
  "candidate_id": "SRC_xxx",
  "from": "P_xxx",
  "to": "P_yyy",
  "rel": "derives_from",
  "candidate_basis": ["basis_relation_present", "same_theme", "lower_region_level"],
  "evidence": {
    "from_title": "...",
    "to_title": "...",
    "from_window": "...",
    "to_window": "...",
    "theme_context": ["power_market"]
  },
  "source": "scripts/analysis_semantic_relations/run.py"
}
```

判定行:

```json
{
  "candidate_id": "SRC_xxx",
  "decision": "accept",
  "confidence": 0.82,
  "reason": "地方政策显式落实上级文件且主题一致",
  "evidence_refs": ["basis_relation_present", "from_window"],
  "model": "minimax-or-deepseek",
  "schema_version": "analysis_semantic_relation_judge.v1"
}
```

输出分层:

- `semantic_relation_candidates.jsonl`:候选。
- `accepted_semantic_relations.jsonl`:仅 accepted。
- `manual_review_queue.jsonl`:需要人工裁决。
- `semantic_relation_summary.json`:数量、失败原因、模型、门禁结果。
- `reports/semantic_relation_preview.html`:中文验收报告。

## 7. 普通模型约束

③-C如果接模型,必须满足:

- prompt 是全局规则,不是 PID 补丁。
- 模型只能判定候选,不能全库自由联想。
- 输出必须过 schema 和 program gate。
- 不确定时进人工池。
- 同一批次记录模型、prompt 版本、schema 版本。
- MiniMax/DeepSeek 是可接入基线;强模型只能做小样本 sentinel 或交叉审计,不能成为正确性前提。

## 8. ④ 的边界

④-A可以先写读取契约,但不能开始真正业务消费。

原因:

- 当前 `analysis_context` 是 v1,只含③-B高精度关系和③-D信号。
- ③-C语义关系尚未纳入。
- 如果④现在做政策卡片或报告,会把“高精度窄关系”误当“完整关系层”。

正确顺序:

1. ③-C机制确认。
2. 等②-B覆盖足够。
3. 跑③-C preview。
4. 生成③-E v2。
5. 再进入④实质消费层 preview。

## 9. 启动③-C的触发条件

满足任一条件才启动③-C preview:

- ②-B已覆盖大部分 tracked policy,且 business_view 是新流程产物。
- 用户批准一个明确子集,例如某主题或某区域,用于③-C小范围验证。
- 需要先做关系机制回归样本,但只能输出 preview,不能 apply。

不满足这些条件时,③-C只保留机制设计,不生成 accepted 语义关系。

## 10. 验收门

③-C preview 必须证明:

- 不写 raw。
- 不写 vault。
- 不 apply。
- 不消费 review queue 或 blocked signals。
- 不直接复用旧 relations 当 accepted。
- 不出现源码 PID 特例。
- 普通模型输出可通过同一 schema 和 program gate。
- `manual_review` 不进入 accepted。
- HTML 明确说明哪些是候选、哪些是 accepted、哪些待人工。
- ③-E v2 只消费 accepted 语义关系,不消费人工池。

## 11. 这次要落地的结论

本次只落机制说明和中文 HTML:

- `docs/superpowers/specs/2026-06-04-analysis-semantic-relations-design.md`
- `docs/reviews/2026-06-04-analysis-semantic-relations-brief.html`

不生成③-C关系,不进入④实质消费。
