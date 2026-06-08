# Stage 1:持续上云管道(Mac 产)设计 spec

> 2026-06-08 · 架构 C 的第一步(路径 A 分阶段)· brainstorming 产出 · 待用户复核 → writing-plans
> 关联:`docs/2026-06-08-pipeline-repo-and-vault-sync-design.html`(总设计稿)、`2026-06-08-hengguan-notification-v1-design.md`(配套消息 spec)

## Goal

把 producer(现 Mac,后期国内常开开发机)产出的 vault,**自动、持续、可靠**地投影到云端 heng-pg,**告别手动 rsync + 手动 run_sync**。生成暂留 producer 本地;本 stage 只解决"产出怎么持续可靠上云"。

成功标准:producer push 一个 vault 变更 → 当天服务器自动 pull + run_sync → DB 反映;无任何手动步骤;失败有可见信号(接配套"消息" spec,过渡期用 `last_sync_run.json`)。

## 非目标(留后续 stage)

- L1/L2 生成迁服务器(C3/C2)— 本 stage 生成仍在 producer 本地。
- vault 服务器可写 + 回流 Mac(C1)— 服务器本 stage 只读消费 vault。
- RSS 国内常驻节点(C4)。
- producer 从 Mac 迁到常开开发机 — 机制与本 stage 完全相同(只换 push 的机器),不阻塞。

## Architecture

```
Producer(现 Mac → 后期国内常开开发机)
  └─ 产 vault → 自动 commit+push ─▶ GitHub: ZaynShao/energy-policy-analysis(vault 仓)
                                       ▲                 ▲
Tokyo 服务器 ── host cron 每天1次 ─────┘                 │
  ├─ git fetch;远端 HEAD 变了才 git pull(写 /root/policy-vault)
  ├─ docker compose run --rm pipeline run_sync(容器读 :ro vault → 写 heng-pg)
  └─ 失败 → 写一条 Notification 进 heng-pg(配套消息 spec;过渡期仅 last_sync_run.json)
Mac(只读阅览)──── git pull ─────────────────────────────┘ → Obsidian 看最新
```

**GitHub vault 仓 = 中枢**:producer 推,Tokyo + Mac 各自拉。三方解耦。

## Components

### 1. vault git 传输(C0:替 rsync)
- vault 已是 git 仓,remote `github.com/ZaynShao/energy-policy-analysis`(branch `main`,267M 工作树 + 119M .git)。
- **Producer 侧**:产出后 **自动 commit + push**。
  - 现状 Mac:沿用现有"里程碑 commit + tag"纪律;push 作为收尾步(可做成产出命令的尾部钩子或本地 cron)。
  - 后期常开开发机:cron 自动 commit+push(常开 → 稳)。
  - 决策:本 stage 不强制改 producer 的产出流程,只要求"产出后 vault 有 push 到 GitHub";自动化程度按机器而定。
- **服务器侧**:Tokyo 从 GitHub **clone** vault 到 `/root/policy-vault`(替掉现 rsync 快照)。
  - 需服务器装**只读 deploy key**(GitHub repo → Deploy keys,read-only;私钥在服务器 `~/.ssh`,chmod 600,不入仓)。
  - 建议 `git clone --depth=1`(浅克隆省盘;服务器仅剩 ~4G,.git 全量 119M)。注意:浅克隆 + 后续 `git pull` 需用 `git fetch --depth=1 origin main && git reset --hard origin/main`(避免浅历史 pull 报错)。
  - ⚠️ 迁移注意:当前 `/root/policy-vault` 是 rsync 来的非 git 目录 → 需先备份/移走,再 clone(或在该目录 `git init` + 关联 remote + reset)。一次性切换,记进 plan。

### 2. 服务器 cron + sync_tick(新脚本)
- 新脚本 `scripts/service/sync_tick.sh`(pipeline 仓):
  1. `cd /root/policy-vault`
  2. `git fetch --depth=1 origin main`
  3. 比较本地 HEAD 与 `origin/main`:**相同 → 退出(不空跑)**;不同 → `git reset --hard origin/main`(浅克隆下等价 pull)。
  4. `docker compose -f docker-compose.server.yml run --rm policy-pipeline python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1`
  5. 读 run_sync 退出码 / `last_sync_run.json` 的 `errors`:**非空 → 触发告警**(配套消息 spec:写 Notification;过渡期:stderr + 保留 last_sync_run.json)。
  6. 全程 append 日志到 `/var/log/policy-pipeline/sync_tick.log`。
- **host cron**:每天 1 次,**建议晚间(如 `0 21 * * *`),即 producer 当天产完之后**,确保拉到当天产出(凌晨跑只会拉到前一天的,故不取凌晨);具体时间用户可调。host cron 而非容器内 cron(host 持有 vault git + docker)。
- run_sync 本身**不改**(已审过:读 vault → upsert heng-pg,幂等,override 守卫)。本 stage 只是把它**调度化 + 串在 git pull 后**。

### 3. 目标 DB
- **先 staging**(`hengguan_staging`):`pipeline.env` 的 `DATABASE_URL` 指 staging;cron 跑通、数据对账(预期 767/998 级别,随 vault 增长)。
- **cutover 后指生产**(gate:PR #14 合并 + 用户拍 TRUNCATE):改 `pipeline.env` 的 `DATABASE_URL` → hengguan。cron 不变,自动持续上生产。cutover 本身是 service-deploy 线既定的一次性步骤(pg_dump 备份 → migrate deploy → TRUNCATE → 首 sync),不在本 stage 重复设计。

### 4. 失败可见
- 主路:配套"消息" spec(run_sync 失败 → 写 Notification → 管理员在 hengguan 看到)。**次序:管道先上 staging,告警暂用 `last_sync_run.json` + 日志;消息功能并行做,cutover 前接上。**
- `last_sync_run.json`(已有)每轮写:synced/relation/skipped_invalid/errors。
- sync_tick.log 保留近 N 天(logrotate 或脚本内裁剪)。

## Data flow(一次 tick)

1. cron 触发 sync_tick.sh。
2. git fetch;HEAD 未变 → 退出(日志记 "no change")。
3. HEAD 变 → reset 到 origin/main(vault 更新到最新)。
4. 容器 run_sync 读 `/vault` → upsert heng-pg(policies + relations)→ 写 last_sync_run.json。
5. errors 空 → 日志记成功 + 计数;errors 非空 → 触发告警通道。

## Testing / 验收

- **单元**:sync_tick 的 HEAD-比较逻辑可抽成一个可测函数(给定 local/remote sha → 决策 pull or skip);run_sync 已有测试不动。
- **集成(staging)**:
  1. producer push 一个小 vault 变更 → 等 cron(或手动跑 sync_tick)→ staging DB 出现该变更。
  2. 无变更时跑 sync_tick → 日志 "no change",DB 不动,无空 sync。
  3. 造一次 run_sync 失败(如临时坏 DATABASE_URL)→ 退出码非 0 + last_sync_run errors 非空 + 告警触发(过渡期看日志/stderr)。
- **幂等**:连续两次 tick 同一 HEAD → 第二次 skip。

## Risks / 约束

- **服务器磁盘 ~4G**:vault 工作树 267M + .git(浅克隆后小)+ 镜像。浅克隆 + 不留多余历史。监控盘。
- **deploy key 安全**:只读、私钥服务器本地 600、不入任何仓。
- **producer 不常开(现 Mac)**:Mac 不开时不 push,服务器拉不到新 → 当天不更新(可接受;迁常开开发机后消失)。
- **首次切换** `/root/policy-vault` rsync→git 是破坏性操作(删/换目录)→ plan 里做成带备份的一次性步骤。
- **cutover gate** 不在本 stage:staging 跑通 ≠ 生产可见,生产仍等 PR #14 + TRUNCATE。

## 落地物

- 新:`scripts/service/sync_tick.sh` + 其可测决策函数 + 测试。
- 服务器:deploy key、`/root/policy-vault` 切 git、host cron、logrotate。
- 文档:`OPERATIONS.md` 补 Stage 1 运维节(cron/切换/回滚)。
- 配套:hengguan 消息 spec(并行)。
