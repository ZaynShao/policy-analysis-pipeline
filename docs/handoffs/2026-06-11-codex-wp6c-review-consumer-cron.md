# Codex 交接：WP-6c l1_review_consumer 接 cron（runbook + 服务器，一包）

**背景**：B14 三模块（`scripts/l1_review_consumer/`：envelope/sync_l1_pool/poll_l1_verdicts）代码+单测全齐，零接线。**applier 已决策推迟**（roadmap 决策表 #5），本包只接传输：forward（state pool→PG IN）+ reverse（PG OUT→verdicts sink）。两模块以 env `DATABASE_URL` 连 PG（服务器 `/etc/policy-pipeline/pipeline.env` 已有，**值盲**），入口为 `python3 -m scripts.l1_review_consumer.sync_l1_pool` / `...poll_l1_verdicts`（确认模块可 `-m` 执行；若无 `if __name__` 入口，加最小入口并配红绿测试——除此外不许改两模块逻辑）。

**纪律（红线）**：凭据值不打印不进 git；不碰 vault；两模块只读 pool/写 sink/读写 PG 队列表，不需要 producer 锁；TDD 仅当需加 `-m` 入口时适用；既有未跟踪文件不碰；本地改动不合 main 不 push（留审计）。

**分支**：`wp6/review-consumer-cron`（从 main 最新起）。

## 改动 · runbook 两行

§1 新增（host python，source pipeline.env 取 DATABASE_URL + notify.env）：

```
# 10:05 L1 review 池前送(state pool→heng PG;池空=no-op)
5 10 * * * cd /root/policy-pipeline-src && (set -a; . /etc/policy-pipeline/pipeline.env; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.l1_review_consumer.sync_l1_pool) >> /var/log/policy-pipeline/review_consumer.log 2>&1
# 每 30 分钟(08-22 时)拉回裁决(PG→state/l1_review/verdicts.jsonl;无裁决=no-op)
*/30 8-22 * * * cd /root/policy-pipeline-src && (set -a; . /etc/policy-pipeline/pipeline.env; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.l1_review_consumer.poll_l1_verdicts) >> /var/log/policy-pipeline/review_consumer.log 2>&1
```

（若模块失败语义需要 `|| notify` 包装，按 deadletter_alert 行风格补；池文件不存在应优雅 no-op——若现状会抛异常，允许加最小防御+测试。）

## 服务器步骤

1. pull main（含本分支合并后由 Claude 通知的 HEAD——**本包先做本地侧，commit 后停下回报**；服务器接线待 Claude 审计合 main 后在回报里给出"续跑指令"再做，或 Claude 另发 resume）。
2. （resume 时）部署 → 手跑两模块各一次（pool 空/无裁决场景，期望优雅 no-op，记录输出）→ 装两行 cron → 核验计数。

## 回报

stdout：分支、commit、是否需要加入口/防御及对应红绿、runbook 两行全文。无需 report 文件。
