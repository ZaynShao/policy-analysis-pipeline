# Pipeline 服务层

增量派生机器 + sync 层。详见 spec `docs/superpowers/specs/2026-06-06-service-deploy-design.md`。

## 组件
- `hash_ledger` 增量账本（content-hash + pipeline_version）
- `l1_status` L1 运行锁（唯一运行信号，不用进程存活判断）
- `l2_queue` 持久化优先级队列（manual=high 插队，cron=normal 批量）
- `orchestrate` L2 编排（队列→归属增量→[结晶/分析钩子]→账本→排空后 sync）
- `../sync/run_sync` vault 派生产物 → heng-guan PostgreSQL upsert

## 本地集成冒烟（需本地 Postgres + 已 apply heng-guan schema 迁移）
```bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
DATABASE_URL=postgres://localhost/heng_dev \
  python3 -m scripts.sync.run_sync \
  --vault "/path/to/vault" --state-dir state/service --pipeline-version 1
cat state/service/last_sync_run.json
```

## 关键纪律
- sync 只 upsert，不删除；不碰 pipelinePid IS NULL 的手动录入记录。
- importance 不踩人工 override（SQL CASE 守卫）。
- 分析(语义关系)Phase 1 不增量；③-C apply 后再设计增量-pairwise。
- 列名对齐 heng-guan Prisma schema（spec §5.1），任一侧改动同步 spec §5。
