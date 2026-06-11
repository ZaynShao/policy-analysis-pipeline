# WP-0 基线清单（2026-06-11，全只读侦察）

> 闭环 roadmap：`docs/superpowers/plans/2026-06-11-cloud-closure-roadmap.md`。本文 = WP-0 验收门产物。
> 数据口径：vault `origin/main @ d716a959`（fetch 后直读远端引用，未动 Mac 工作区）；VPS 运行时 state 只读实查。

## 1. ③ 补课集合：361 篇

- 6/6 关系重建 commit = `a6fb3c09`（"③-apply：459 反链页 + canonical，换掉 5/8+5/12 stale"）。
- 之后新增政策 = **361 篇**（`git -c core.quotepath=false diff --diff-filter=A --name-only a6fb3c09..origin/main -- 0_raw/policies`，排除 _archive/_duplicates）。
- 361 篇全部有 frontmatter id。**其中 326 篇无 business_view**。
- 观察：含市监失效类噪声（天津食品许可等"（失效）"条目）——L1 gate 域问题，不影响 ②③ 机制；WP-1 backfill 时顺手统计 gate 不过率。

## 2. ③-C 成本：增量 407 对，全量也仅 1019 对（成本焦虑解除）

本地实跑 ③-B preview（纯 regex 零 LLM，1224 篇语料数秒完成）：

- 全量候选对 = **1019**（references 614 / cites_basis 247 / supersedes 6 / clarifies 152）。
- 涉及补课 361 篇的增量候选 = **407**（references 224 / cites_basis 101 / clarifies 81 / supersedes 1），与现存 canonical 1138 边**零重叠**。
- ③-C（deepseek-v4-flash 判候选对）：补课一次性 ≈ 407 次调用，成本忽略不计；日常稳态新政策 1~35/日 → 每日个位到几十对。
- 结论：**夜间增量制成本无虞**；全量重判保留为手动兜底也有界（1019 对）。

## 3. 缺口对账（对到个位，全部咬合）

```
raw 1224 = 863(6/6 前存量) + 361(6/6 后新增)
business_view 800
无 business_view 424 = 326(补课集合内) + 98(6/6 前存量)
投影 synced 792 = 800 − 8(skipped_invalid)
relation 投影 992 / canonical 1138 → 146 边悬挂(一端政策未投影被 run_sync 跳过)
commentary 投影 171;l2_queue 0;死信文件不存在(无失败)
```

- 146 悬挂边 ⇒ **WP-1 backfill 完成后部分关系边会自动恢复投影**——证明 WP-1 先于 WP-2 验收的顺序正确。
- 附：1224 个文件 → 1213 个唯一 pid（≈11 个重复 pid 双文件 wart，S3 既记项，不扩大）。

## 4. l1_review_consumer 状态（归 WP-6）

- B14 模块三件齐：`envelope.py`（标准信封+幂等键）/ `poll_l1_verdicts.py`（PG 读 OUT 裁决→sink）/ `sync_l1_pool.py`（IN 池→PG 写）。纯逻辑可单测，PG 侧仅需 `DATABASE_URL`（VPS pipeline.env 已有）。
- 衡观表已部署（PR#14/16/17）。缺的只是 VPS 两条 cron 接线 + verdict 应用步（裁决落 vault 的 apply 链路）核实。

## 5. 四产物族盘点（WP-5 输入）

| 族 | 现状 | 陈旧度 | 生产者 |
|---|---|---|---|
| policy_summaries.jsonl | 934 行，契约 SCHEMA §5.1 | 696 配当前 pid / **238 失配**（pre-②-A 旧 id）| **无**（scripts/l2_derive 已空）|
| policy_classification.jsonl | 51 行 | 仅 32 配当前 pid——早期小实验 | **无** |
| entities/ | registry.yaml **活**（②-B 词表收口维护中）；_extractions.jsonl 7009 行 | _extractions 为建设期产物 | registry 在 ②-B 产线内；_extractions 无 |
| opinions/ | 76 个 per-policy 观点页 | 建设期产物 | **无**；与四层设计"评论=校准信号不外显观点"存在取代关系 |

- 四族重建全部属于"新建设"（不是搬运）；每族 mini-spec 进 WP-5。
- ⚠️ 待用户裁决：opinions 去留；classification 契约是否保留（51 行实验体量）。

## 6. 工具事实（WP-2/3 handoff 直接引用）

- ③-B：`python3 -m scripts.analysis_high_precision_relations.run preview --vault V --state P`（输出 summary json + candidates jsonl + html 报告；tracked-only 基线）。
- ③-C：`preview --vault V --state P --hpr <③-B candidates.jsonl> --judge-model deepseek-v4-flash`。
- ③-D：`preview --vault V --sem … --hpr … --out …`（默认 preview 只写 state；**apply 步不存在 = WP-2 要新建的 runner**）。
- canonical 边字段：`from/to/rel/confidence/evidence/source`。
- l2_queue：`enqueue_batch(path, pids, trigger, priority, …)` 为函数（无独立 CLI），入队走 2026-06-10 recover handoff 的既验证模式。
