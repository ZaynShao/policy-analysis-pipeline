# ③-B 高精度政策关系 preview 设计

## 1. 定位

③-B 是③分析层的高精度政策关系 preview。它只处理四类关系:

- `references`:正文显式文号引用。
- `cites_basis`:opening 依据段中的显式制定依据。
- `supersedes`:正文明确废止、同时废止、停止执行或取代。
- `clarifies`:标题或正文明确实施细则、操作指引、申报指南等细化关系。

本步骤不处理 `derives_from`、`aligns_with`、`extends`、`iterates` 等语义关系。

## 2. 输入

- 只读 vault 当前 git tracked 的 `0_raw/policies/*.md`。
- 只读每篇政策 frontmatter 的 `id`、`aliases`、`title`、`official_number`。
- 只读正文内容。
- 旧 `1_extracted/relations/*.jsonl` 不能作为 accepted 输入;本步骤可以在 HTML 里说明它们只用于历史对照,但第一版实现不读取旧关系。

未跟踪 raw 必须排除并单独计数。

## 3. 输出

Preview 输出到工程库:

- `state/analysis_layer/preview_20260604/high_precision_relation_summary.json`
- `state/analysis_layer/preview_20260604/high_precision_relation_candidates.jsonl`
- `state/analysis_layer/preview_20260604/policy_relation_candidates/{references,cites_basis,supersedes,clarifies}.jsonl`
- `state/analysis_layer/preview_20260604/reports/high_precision_relation_preview.html`

不写 vault,不写 raw,不 apply。

## 4. 抽取规则

先建立 current raw 文号索引:

- 只索引非空 `official_number`。
- 统一压缩空白。
- 文号作为候选目标,命中正文后只允许指向当前 tracked raw 中可定位的 policy。

候选分类:

- 任意正文命中文号且不是 self-link → `references`。
- 命中位置在 opening 800 字符内,且窗口含 `根据`、`依据`、`贯彻`、`落实`、`按照`、`结合实际` 等依据语义 → `cites_basis`。
- 命中窗口含 `废止`、`同时废止`、`停止执行`、`失效`、`取代`、`替代` → `supersedes`。
- 源标题或命中窗口含 `实施细则`、`操作指引`、`申报指南`、`办事指南`、`解读`、`细则` 等细化语义 → `clarifies`。

同一 `from/to/rel/doc_number` 去重。

## 5. 候选行格式

每行包含:

- `candidate_id`
- `from`
- `to`
- `rel`
- `doc_number`
- `evidence`
- `location`
- `confidence`
- `from_path`
- `to_path`
- `rules`
- `extracted_by`
- `schema_version`

`extracted_by` 固定为 `scripts/analysis_high_precision_relations/run.py`。

## 6. 模型约束

第一版不调用模型。

后续若引入模型复核,只能作为普通模型可跑的受限判定层,必须经过 schema、program gate、审计门和人工池阻断。不能依赖强模型自由发挥,不能用 PID 补丁。

## 7. 验收门

- 测试证明未跟踪 raw 被排除。
- 测试证明 opening 依据引用产出 `references` 和 `cites_basis`。
- 测试证明废止语句产出 `supersedes`。
- 测试证明实施细则/指南类文本产出 `clarifies`。
- 测试证明输出包含 summary、总 JSONL、四类分文件和中文 HTML。
- 真实 preview 后 vault 状态不变。
