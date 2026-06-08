# B14 → L1 applier handoff:verdicts.jsonl 回灌接口契约

> 反向 handoff(对称于 L1 给 B14 的 IN handoff)。
> **B14(我)** 建到「人审 verdict → 标准信封落 `state/l1_review/verdicts.jsonl`」为止。
> **L1** 建正式 applier:消费该文件,按 kind 执行回灌 apply。
> 过渡期:沿用现有 oneshots(不读 verdict,自己重判),见末节。

## 1. 输入:`state/l1_review/verdicts.jsonl`

每行一条标准信封(B14 `scripts/l1_review_consumer/envelope.py` 产出):

```json
{
  "envelope_v": 1,
  "pool": "l1_source_quality",
  "ref": "<channel|pid|url>",
  "kind": "gate|checkpoint|sweep|fetch_fail",
  "verdict": "<见下表>",
  "corrections": { "corrected_label": "...", "retry_params": {...} },
  "reviewer": "<衡观 user>",
  "note": "<人备注>",
  "decided_run": "<衡观批次>",
  "decided_at": "<ISO8601>",
  "idem_key": "<kind:ref:decided_run>",
  "applied": false,
  "applied_at": null,
  "apply_result": null
}
```

## 2. 每 kind 的 verdict → apply 动作(L1 owns 语义)

| kind | verdict | apply 动作 | 附带字段 |
|---|---|---|---|
| `gate` | `pass` / `commentary` / `reject` | 暂存 ext 项 → `policies/` / `commentaries/` / 弃 | `corrections.corrected_label` 可选 |
| `checkpoint` | `promote` / `drop` | 渠道候选 → 验证(进 backfill)/ 移除候选 | — |
| `sweep` | `confirm` / `keep` | `git mv policies/↔commentaries/`(§C 确定性重分类)/ 不动 | — |
| `fetch_fail` | `retry` / `unfetchable` / `drop` | 重入抓取队列 / 标 unfetchable / 跳过 | `corrections.retry_params` 可选 |

## 3. applier 必须守的 3 条(继承语义,B15 终审)

1. **重核不盲信(语义①)**:apply 前重新核验,不照搬 verdict 当事实。尤其 `fetch_fail` 判 `retry` 时——**实际重抓,确认成功才视为已修复**;仍失败则保留/回写 `apply_result=still_failing`,不能盲信已 drop。
2. **回填审计**:apply 成功后,把该条 envelope 的 `applied=true` / `applied_at` / `apply_result` 回写(就地重写 `verdicts.jsonl` 或落 `verdicts.applied.jsonl`)。**消费按 `applied==false` 过滤,幂等**(配合 `idem_key`)。
3. **review/ GC(语义②衍生)**:apply 成功后,清 `state/T1_incremental/review/` 对应暂存项(IN-only 不自清)。

> 注:池删行(`state/l1_review/pool.jsonl` 判完即出池)已由 B14 的 `poll_l1_verdicts.remove_from_pool` 做掉,applier 不重复。

## 4. 过渡期(B14 信封/消费链未全线上前)

现有 oneshots 照常可用,**但它们不读 verdict、自己重判/硬编码**:
- `scripts/_oneshot/promote_checkpoint_channels.py`(checkpoint promote)
- `scripts/_oneshot/sweep_existing_commentary.py`(sweep,`APPLY=1`)

正式 applier 上线后,改为消费 `verdicts.jsonl` 的人审结论,替代「自己重判」。

## 5. 纪律

§C(LLM 判定不写 raw;`gate`/`sweep` 的 raw 移动是确定性重分类,§C 内合规)+ dry-run before apply + 不打 PID 补丁。
