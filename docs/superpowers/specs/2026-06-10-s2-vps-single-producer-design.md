# S2 · VPS 单生产者全自动编排 — 设计

> 状态:已与用户逐段确认(2026-06-10)。
> 前置:S1(vault 双写基座:可写 key + sync_tick 防误删守卫)已完成并验证。
> 决策记录:RSS 经中转架构实测不需代理且代理对其无效(wewe-rss 用 got 11);
> 东京 VPS 裸跑登录已被 weread 接受 → 评论线直接 VPS 跑。

## 1. 目标

把 #34 大迁移的 producer 角色全面翻转到东京 VPS:L1 政策、L1 评论、行业信息分流、
L2 派生、vault 写权威、DB 投影全部在 VPS 单机闭环;Mac 退役为 git pull 只读阅览 +
热备,零定时任务。目标形态为**全自动 cron**(即启用 OPERATIONS §3 一直未落地的
「维护期」目标态),人只处理告警与审核。

## 2. 目标态(VPS 时刻表)

```
07:00  wewe-rss discovery(容器内置 cron,已上线)
07:30  评论 ingest(policy-pipeline 容器)→ 写 vault commentaries → produce_and_push
09:00  L1 政策 run_incremental(容器)→ 写 vault policies → produce_and_push → enqueue L2
09:30  L2 run_l2 drain(容器)→ business_view 等派生 → 写 vault → produce_and_push
10:00  run_sync 投影 heng-pg(生产完即投影,不等晚间)
21:00  sync_tick 照旧:外部变更兜底拉取 + S1 防误删守卫(不动)
每 6h  token 检测;每日 09:30 QR relay 哨兵(openclaw→飞书)
告警   所有自动化入口失败 → openclaw 飞书文字
```

节奏沿用既定决策(07:00/07:30/6h 为 2026-06-08 拍定;09:00 为 OPERATIONS 维护期
目标态),不另发明。

## 3. 新组件(全 TDD)

### 3.1 produce_and_push(scripts/service/,新模块)
生产后的 git 收尾,所有生产 cron 共用:
- add(白名单路径,由调用方按产线传入:评论线 `0_raw/commentaries/`;政策线
  `0_raw/policies/`;L2 线 `1_extracted/ _meta/business_view/ 2_crystallized/`;
  白名单外出现改动 = 异常,告警不提交)→ commit(规范 message,标注产线)→
  `pull --rebase` → push
- 空变更 = no-op(exit 0);push 失败 = 告警 + **保留本地 commit**(下轮重试;
  期间 sync_tick 守卫对 local_ahead>0 会 abort 而非 reset——S1 正好接住此场景)
- 纯函数核心 + CLI 壳,tmp git repo 测试

### 3.2 commentary ingest `--since` 日期下限
- 新参数 `--since YYYY-MM-DD`:date 早于下限的 feed item 直接跳过
- 动机:vault 评论存量 485 篇、覆盖至 2026-06-07;比存量更早的 ~2300 篇 wewe DB
  历史**不补**(留在 wewe-rss DB,需要时再说)
- 首跑 `--since 2026-06-07`,缺口仅数日

### 3.3 L1→L2 队列接线
- `run_incremental` 完成后,把本轮新入库 pid `enqueue_batch` 进 L2 队列
  (trigger="l1_incremental")——当前 enqueue 无任何 L1 侧调用方,是断点

### 3.4 fetcher 代理运行时兜底(零配置、零探测、零标志)
```
直连(既有 firecrawl→trafilatura→bs4 链)
  ├─ 成功且内容合格 → 用
  └─ 网络错/超时/4xx/5xx 或内容垃圾(既有质量门)
       └─ 配了 POLICY_FETCH_PROXY_URL → 经代理重试一次 → 仍败才 fetch_error
```
- 不配 env = 纯直连,行为与现状完全相同;新渠道零成本延展;站点行为变化自愈
- 抓取记录加 `via_proxy` 字段(观测代替配置)
- **回归测试**:有 proxy env 时只有 L1 fetch 路径吃它;sync/L2/LLM/vault-sync
  不继承(proxy runbook 既定纪律)
- 已否决的替代方案:全渠道探测矩阵 + per-channel 标志(标志腐烂、新渠道需人工
  工序、机件多);全局走代理(隧道成全采集 SPOF)。connectivity_probe 留作手工
  诊断工具,不进系统。

### 3.5 QR relay / token 哨兵迁 VPS
- daily_check + relay cron 化上 VPS;openclaw→飞书原样平移(凭据用户落)
- 依赖本日已修的 account.add 落库步(v2.6.1 上 getLoginResult 只读不落库,
  必须显式 account.add upsert;刷新失效账号与新增账号同链路)
- Mac launchd(com.zayn.policy.wewe-qr-relay-daily)在 VPS 哨兵验证后下线

### 3.6 cron 接线 + 告警 helper
- host crontab,照 sync_tick 现有风格(日志 /var/log/policy-pipeline/ + logrotate)
- 失败告警统一走 openclaw 文字推送(helper 供各入口复用)

## 4. 凭据落位(用户亲手,全 out-of-git,不过聊天)

| 文件/位置 | 内容 |
|---|---|
| /etc/policy-pipeline/models.env | OPENAI_API_KEY / OPENAI_BASE_URL / JUDGE_MODEL(+可选 FIRECRAWL_API_KEY / TAVILY_API_KEY) |
| openclaw on VPS | openclaw 安装 + 飞书凭据 |
| /root/wewe-rss/.env | WEWE_AUTH_CODE(已在,复用) |
| /etc/policy-pipeline/fetch-proxy.env | POLICY_FETCH_PROXY_URL(政策线兜底用;评论线不用) |

## 5. 上线波次(每波验证过再进下一波)

- **W0 前置**:commit 既有修复(qr_relay account.add + pyproject deps)→ 合 main
  → 服务器 git pull + `docker compose build`(镜像现缺,需 rebuild);凭据落位;
  Mac 推残留 2 个 vault commit(脏数据清理 + 文档;用户亲手——注:其中删除的
  15 条市监脏政策因 upsert-no-prune 会在 DB 留孤儿,记入 S3 cleanup,不在本期)
- **W1 评论线全自动**:ingest 首跑 `--since 2026-06-07`(监督式)→ cron 接线
  (07:30 + token 6h + QR relay 09:30)→ Mac launchd 下线
- **W2 L2 + 投影链**:run_l2 在 VPS 首次真跑(监督)→ L1→L2 接线生效 → 10:00 投影
- **W3 政策线**:fetcher proxy-fallback 落地 → `run_incremental --dry-run` →
  **用户手动触发一轮完整 L1 做验证**(监督真跑,首周人工抽查 policy_gate 判定)
  → cron 09:00
- **W4 cutover(=原 S4 收尾)**:全量 drift 核对 → OPERATIONS 改版(§3 维护期
  启用 + §8 重写为单生产者)→ Mac 正式退役(只读阅览 + 热备)

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| LLM gate 无人值守误判/烧钱 | JUDGE_MODEL=deepseek 级;review_pool 旁路;W3 首周人工抽查 |
| vault 变机器高频 commit | push 前 rebase;Mac 只读不冲突;message 规范可审计 |
| 跨墙隧道抖动 | 代理仅是运行时兜底,直连通的渠道无感;隧道挂 → 长尾渠道 fetch_error + 告警,不连坐 |
| 微信风控 | discovery 频率不变(每天 1 次);token 哨兵闭环已含落库修复 |
| 自动化静默挂 | 每入口失败→飞书告警;last_run 状态文件;sync_tick 守卫兜底 |
| 评论重复入库 | seen 集(vault URL)+ `--since` 下限双保险;Mac 未推 commit 已查明不含评论 |

## 7. 范围外

- S3:③ 关系增量 apply、DB 孤儿清理(含 W0 那 15 条)、评论↔政策建模
- market_intel B1(继续暂存 state)
- hengguan 内建 Notification 正式告警(待建 PR;本期告警走 openclaw)
- 政策 drift 深度 backfill 之外的历史评论补抓
