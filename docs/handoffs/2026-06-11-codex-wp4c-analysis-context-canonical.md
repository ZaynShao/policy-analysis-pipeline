# Codex 交接：WP-4c analysis_context 兼容 canonical 输入（本地代码侧，小包）

**背景**：WP-4b Step 2 失败（report `2026-06-11-codex-wp4b-report.md`）：`analysis_context`（6/4 设计期）要求关系行带 `candidate_id` 且 rel ∈ {references, cites_basis, supersedes, clarifies}，而正式产物 `relations_canonical.jsonl`（6/6 定型）行为 from/to/rel/confidence/evidence/source，rel 共 8 种（references 614 / aligns_with 515 / cites_basis 247 / clarifies 152 / derives_from 107 / extends 15 / iterates 13 / supersedes 6）。**650 条边（39%）在旧词表外**。④ 应消费正式产物，按以下最简设计对齐：

1. **candidate_id 回退**：`row.get("candidate_id") or row.get("source")`——canonical 的 `source`（SRC_xxx/HPR_xxx）是逐边唯一稳定 id，天然审计键。两者皆缺才报错（报错语义保留）。
2. **rel 词表**：旧四类专用计数器**完全不动**（向后兼容既有测试/输出）；其余 rel 进每政策 `other_rel_counts: {rel: count}`（按 from/to 两端各计一次，与旧逻辑对称性一致——aligns_with 在 canonical 中已是规范化无向对，两端同计）；**未知 rel 不再 raise**（夜间链不能因词表演化而碎），在 summary.json 增加 `rel_vocabulary_seen`（全量 rel→计数）保持可见。
3. `audit_refs.relation_candidate_ids` 逻辑不变（用上面解析出的 candidate_id）。

**纪律（红线，违者中止）**：TDD 红绿分 commit；只许改 `scripts/analysis_context/`（含其下 schema/聚合代码）与 `tests/analysis_context/`；既有未跟踪文件不碰；不合 main 不 push；不碰 vault。

**分支**：`wp4/analysis-context-canonical`（从 main `aab069d` 起）。

## 测试要求（红 commit）

- canonical 形态行（无 candidate_id、有 source、rel=aligns_with/derives_from）→ 正常聚合：candidate_id 取 source；other_rel_counts 正确；audit_refs 含 source id。
- 旧形态行（带 candidate_id、rel=references）→ 行为与现版完全一致（回归）。
- 两字段皆缺 → 仍 raise candidate_id。
- 未知新 rel（如 "future_rel"）→ 不 raise，进 other_rel_counts 与 summary.rel_vocabulary_seen。

## 验证

`python3 -m pytest` 全绿（585 基线 + 新增）；专跑 `tests/analysis_context/` 全绿。

## 回报

stdout：分支、红绿 commit、pytest 数字、关键 diff 概要。无需 report 文件。
