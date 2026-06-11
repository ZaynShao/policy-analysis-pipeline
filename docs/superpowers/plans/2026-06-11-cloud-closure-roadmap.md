# L1→L2 全栈云上自闭环 · 整体规划（roadmap v2）

> **性质**：roadmap 级整体规划。每个 WP 启动时单独出代码级 handoff（含 TDD 步骤、确切命令）交 Codex，Claude 审收——沿用本项目既定分工。
> **v2（2026-06-11）**：按用户四条裁决修订——①闭环判据从"hengguan 当前投影面"改为"四层方法论产物全集"（L3 地基依赖全集在场）；②结晶查证为建设期产物（2026-05-08 P2.7），归 L3 阶段；③废除 2026-06-11 handoff 自创的 ①-⑧ 平铺编号，全部重锚到四层方法论命名；④③关系改增量制（新政策×存量匹配）。
> **命名准绳**：四层 = ①源到位 ②归属 ③分析 ④消费（`docs/superpowers/specs/2026-06-02-policy-intelligence-four-layer-design.md`）。③ 内部子节点 ③-B/③-C/③-D/③-E 为 2026-06-04/05 spec 既定命名。**评论信号 / 行业情报信号均属③分析层**（四层设计原文：③ = 关系 + 评论校准信号 + 区域差异 + 市场信号验证）。

---

## 0. 第一性原理：闭环判据

**目标（用户口径）**：云上 hengguan 前端可以完整消费 L1 raw 产出 → L2 派生产物；有东西拉在本地，云上就无法自闭环。

**判据的准绳不是 hengguan 当前在读什么。** hengguan 当前的消费是盲目的（只接 `run_sync` 投影面，不知道 L1/L2 的产物路线图）；下一阶段 L3 地基会定义生产规范、hengguan 按规范产出——那一步的前提是 **②③ 产物全集已经在云上持续生产**。所以：

> **闭环判据 = 四层方法论 + SCHEMA 契约定义的 L1→L2 产物全集，每一族都在 VPS 上持续再生产。**
> `run_sync` 投影面只是当前已接通的消费通道，不是范围边界。

三个同时成立的条件：

1. **生产闭环**：产物全集（①源到位三源、②归属、③分析全部子节点）每族在 VPS 有定时任务持续再生产；稳态 Mac 参与度 = 0。
2. **覆盖闭环**：存量无"只有本地建设期产物、云上永不再算"的断层。
3. **可见闭环**：任何一环静默挂掉，24h 内飞书告警。否则"自闭环"退化为"自欺环"。

**为什么过去反复留尾巴（第一性诊断）**：历次规划单位是"事件波次"（S1→W1→W2/W3），范围来自当时记忆里的痛点，不是来自产物全集的盘点；且无机器可查的闭环判据。两个结构性对策贯穿本规划：
- (a) **范围 = 产物族全枚举逐族打勾**（§1 表），准绳是四层设计 + SCHEMA，不靠记忆；
- (b) **闭环审计日巡检**（WP-6）：漏项从回忆问题变成告警问题。

---

## 1. 产物族全枚举与现状

基线事实（2026-06-11 只读侦察 + 溯源核实）：
- 投影目标库 = **生产 `hengguan`**（pipeline.env 实查，staging cutover 已完成）。
- VPS crontab 7 条 active（07:30 评论 / 09:00 L1 政策 / 09:30 ②归属 / 10:00 投影 / QR 哨兵 / 6h token / 21:00 sync_tick），2026-06-11 首个无人值守周期全绿。
- `l1_review_consumer` 不在 crontab（人审回灌无自动消费；B14 阶段1 pipeline 侧已建，衡观表已部署）。
- ③ 关系存量 **2026-06-06 已整体换新**（"③-apply：459 反链页 + canonical，换掉 5/8+5/12 stale"，vault git log）——B10 判定的陈旧存量已清，**现存量可信，增量制地基成立**。
- 结晶 `2_crystallized/` 最后实质更新 = **2026-05-08（P2.7 Tier B 建设期批次）**，四层方法论无结晶节点 → 其角色（主题页/区域视图）= ④消费层，归 L3 阶段接管。
- `scripts/l2_derive/`（summaries/classification 的老生产者）**目录已空**——这两族当前无任何生产者。
- `1_extracted/entities/registry.yaml` 是**活的**（②-B 词表收口在维护）；`_extractions.jsonl` 为建设期产物。
- `1_extracted/opinions/`（per-policy 观点页）与四层设计"评论 = 校准信号、不外显观点证据"路线存在取代关系。

### 产物族状态表（✅=云上自动 ❌=缺 ⚠️=需用户/设计裁决）

| 层 | 产物族 | 云上状态 | 行动归属 |
|---|---|---|---|
| ①源到位 | 政策 raw（165 渠道 incremental）| ✅ 09:00 cron | — |
| ①源到位 | 评论 raw（wewe-rss → ingest）| ✅ 07:30 cron | — |
| ①源到位 | 市场情报第三源（B1：manifest 登记 → 信号）| ❌ ingest 的 market_intel_staging 只暂存，manifest 链路未接 | WP-3 |
| ①源到位 | 人审回灌（hengguan MANAGER 裁决 → vault）| ❌ consumer 未接 cron | WP-6 |
| ②归属 | business_view（②-A/②-B，deepseek）| ✅ 09:30 cron；❌ 存量 424 无归属 | WP-1 |
| ②归属 | L2 失败可见（死信告警）| ❌ run_l2 exit 0、死信无告警 | WP-1 |
| ③分析 | 关系族：③-B 高精度 → ③-C 语义 → ③-D canonical 视图 + 反链页 | ❌ 6/6 全量重建后停更；**apply-to-vault 无 runner**；无增量路径 | WP-2（增量制）|
| ③分析 | 评论校准信号（commentary_signals → derived_signals apply）| ❌ 停更，未进 cron | WP-3 |
| ③分析 | 市场信号验证（market_intel_signals，B1）| ❌ 同上 + manifest 来源接线 | WP-3 |
| ③分析 | ③-E 关系清点（audit）| ❌ | WP-4 |
| ④消费 | 上下文装配（analysis_context / signal_context，为报告/查询接口备料）| ❌ | WP-4 |
| ④消费 | 投影 run_sync → 生产 hengguan | ✅ 10:00 cron | — |
| ④消费 | 主题页/区域视图（结晶的后继，按 L3 生产规范）| ⚠️ L3 阶段定义 | L3 地基（§5）|
| ②/③ | **四产物族**：policy_summaries / policy_classification（SCHEMA §5.1 契约在、生产者已不存在）；entities/_extractions；opinions | ❌ 冻结，无现行 runner；**L3 依赖其在场，进闭环范围** | WP-5 |
| 巡检 | 闭环审计（新建）| ❌ | WP-6 |

**范围外（不混入）**：T1 市级渠道扩容（内容增长，云上跑同一 catalog）；L3 月报渲染；judge 同模型质量（stopgap 挂账）；DB 孤儿清理（S3）。

---

## 2. 工作包切片（每包过验收门才进下一包）

> 交付纪律沿用既定约定：每 WP 完整 Codex prompt 先贴用户过目；审计三层（过关/阶段评估/洞察）；vault 写只经 `produce_and_push` 白名单；凭据不过 Codex。

### WP-0 · 基线核实 + 钉成本（半天，Claude 侦察为主）

1. **③ 增量补课集合钉数**：6/6 关系重建之后入库的政策清单（35+，含 backfill 进来的存量是否已在 6/6 重建语料内——③-B 消费 0_raw tracked，424 无归属政策大概率已在边集内，逐项核对口径）。
2. **③-C 增量成本钉死**：catch-up 集合 × 存量的 ③-B 候选对计数 → deepseek 成本（增量制下成本天然有界，此步是确认不是探险）。
3. 432 投影缺口口径对账（≈424 无 business_view + skipped_invalid，对到个位）。
4. `l1_review_consumer` 实现状态确认（作用域、接 cron 还差什么）。
5. **四产物族盘点**（WP-5 的输入）：summaries/classification 的 SCHEMA 契约现状与老产物质量；entities/_extractions 与 registry 的边界；opinions 的消费者是谁、与评论校准信号的取代关系——每族一段事实陈述。

**验收门**：一页基线清单，五项全部落地成数字/事实。

### WP-1 · 地基修复（1 天，Codex）

无人值守 LLM 自动化之前，失败必须先可见——这是 WP-2/3 的硬前置。

1. **424 归属 backfill**：无 business_view 的存量 pid 全量入队 → run_l2 drain 分批（首批监督）。
2. **L2 失败告警**：死信 `l2_failures.jsonl` 增长 → notify；run_l2 failed>0 行内告警。
3. 死信周度 sweep 回队。

**验收门**：投影 synced 792 → ≈1200+（与 WP-0 口径吻合）；人为投毒一条必失败任务 → 飞书 24h 内收到告警。

### WP-2 · ③ 关系族上云·增量制（1-2 天，Codex；核心缺口）

**架构（用户裁决）**：增量只和存量匹配，工程量可控。存量 = 6/6 重建的可信边集。

1. **一次性补课**：WP-0 钉出的 catch-up 政策 × 存量跑一轮（③-B 圈候选 → ③-C 判新增候选 → ③-D 增量并入 canonical + 反链页）。
2. **新建增量 apply runner**：把 ③-D 产物写 `1_extracted/relations/`（补上"由人另控"的缺失步）→ `produce_and_push --whitelist 1_extracted/relations/`。
3. **日常增量**：当日新政策（来自 L1→L2 队列同源的 pid 集）× 存量，挂夜间 cron（02:00，共持 producer flock，与白天线错峰）→ 次日 10:00 投影自动带上。
4. 全量重建保留为手动兜底工具（不进 cron）。

增量制同时化解 upsert-no-prune 的主要张力：日常只增边不重生边集；政策废止引发的边失效走标记/清理，记 S3 不在本期扩大。

**验收门**：relation_count 从 992 恢复增长；E2E：一条新政策云上入库后 48h 内在 hengguan 看到其关系；CLI 参数逐个对源码复核（测绘表有推断成分）。

### WP-3 · ③ 信号线上云（1 天，Codex）

1. **评论校准信号**：commentary_signals preview（确定性）→ derived_signals apply（preview→apply 机制现成）→ produce_and_push → 夜间 cron。run_sync 已会消费 commentary_signals.jsonl（软引用设计），投影侧零改动。
2. **市场信号验证（B1）**：评论 ingest 已有的 market_intel_staging 分流 → manifest 登记链路接通（按 2026-06-03 spec）→ market_intel_signals → derived_signals 的 market 半边。若 manifest 登记环节需要人工裁决位，按 spec 留人工池，不阻塞评论校准信号先行。

**验收门**：投影 commentary_count 增长；新评论 → 校准信号 → 生产 hengguan DB 全程零 Mac。

### WP-4 · ④ 上下文装配 + ③-E（0.5 天，Codex；全确定性零 LLM）

signal_context → analysis_context → ③-E inventory 挂夜间 cron 末尾。这是④消费层（报告/查询接口/未来 L3 规范）的备料层，跑了就有。

**验收门**：夜间链一次跑通，各层产物时间戳均为 VPS 当日。

### WP-5 · 四产物族重生产线（每族 0.5-1 天，Codex；以 WP-0 盘点为输入）

L3 地基依赖产物全集在场，四族进闭环范围，每族 mini-spec → runner → 增量 cron：

1. **policy_summaries**（SCHEMA §5.1 契约在）：新政策逐篇摘要（LLM，增量制：只产新增 pid），存量回填一次性分批。
2. **policy_classification**：同上模式。
3. **entities**：registry.yaml 已活在 ②-B 维护里；_extractions 按盘点结论决定重生方式或并入②产线。
4. **opinions**：⚠️ 与"评论=校准信号"路线的取代关系按盘点结论 + 用户裁决（L3 是否需要 per-policy 观点页）定重生或正式由 commentary_signals 接替。

**验收门**：每族有 cron、有产物更新、有失败告警；存量回填口径对账。

### WP-6 · 闭环收口 + Mac 退役（0.5 天，Codex + 用户）

1. **闭环审计日巡检**：每日核查 (a) §1 表每个 ✅ 族的 vault 最新 commit 作者 = `policy-pipeline-vps` 且 age < 族阈值；(b) 各 cron 日志当日 success；(c) `last_sync_run.json` errors=[]。任一不满足 → 飞书告警。**"忘了上云"从此是监控告警，不是回忆测验。**
2. `l1_review_consumer` 接 cron（按 WP-0 状态）。
3. OPERATIONS §8 重写为单生产者终态；Mac 退役为只读阅览。
4. **终极验收（闭环演习）**：Mac 关机 48h，云上完整跑两个周期，hengguan 数据照常更新，飞书静默=健康。

---

## 3. 节奏架构（最简版）

- **白天增量线（已有，不动）**：07:30 评论 → 09:00 L1 → 09:30 ②归属 → 10:00 投影。
- **夜间增量线（新增）**：02:00 起 ③关系增量 → 信号线 → 上下文装配 →（WP-5 后）summaries/classification 增量，共持同一把 flock；每层失败 → notify 且不阻断次日白天线。
- 实现沿用已验证的"cron 行 + produce_and_push 白名单 + flock"模式，**不新建大编排器**；orchestrate.py 整合留作日后可选优化。

## 4. 与 L3 地基的衔接（下一阶段入口，不在本规划内实施）

本规划完成 = ②③产物全集云上持续生产 = L3 地基的前置条件成立。L3 阶段：定义生产规范（决策卡片/主题页/区域视图/查询接口 = ④消费层正式化），hengguan 按规范产出；结晶（2_crystallized，建设期 P2.x 手工产物，2026-05-08 后冻结）的角色由该规范接管，现有 4 篇作为历史数据保留。

## 5. 残留决策项

| # | 决策 | 状态 |
|---|---|---|
| 1 | opinions 去留 | ✅ 用户裁决（2026-06-11）：**放弃**。commentary_signals 正式接替，76 页冻结归档，不进闭环判据 |
| 2 | classification 去留 | ✅ 查证后废弃（2026-06-11）：**它不是产物族**，是 T2a 清理把建设期 B7_subagent 倒灌 raw 的标签搬出来的残渣（每行 source=`policy_raw_frontmatter_pre_t2a_migration`），零生产者零消费者；其职能由 L1 policy_gate 承担。51 行留档作 S3 垃圾清理线索 |
| 3 | manifest 登记的人工裁决位形态（B1 spec 已有人工池设计，确认即可）| ✅ 用户裁决（2026-06-11）：**market_intel 增长线放弃**（"略有价值的尾巴，不在意"）。保留 23 行存量 manifest 每晚确定性再生产（derived_signals 链输入需要，零成本）；**不建** staging→manifest 登记器、**不设计** raw 域、**不加**积压提醒。staging 命中静默积存 /state，无害。事实佐证：路由过滤器上线至今零命中（服务器+Mac staging 均空）|

⇒ **WP-5 范围收敛为两族**：policy_summaries 重建（契约 SCHEMA §5.1 在、生产者缺位）+ entities/_extractions 处置（registry 已活在 ②-B）。

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| ③-C 增量成本 | 增量制天然有界（新×存量，③-B regex 收窄）；WP-0 计数确认 |
| 无人值守 LLM 静默失败 | WP-1 告警先行，硬前置 |
| 政策废止边失效（upsert-no-prune）| 增量制只增边；失效走标记，S3 不扩大 |
| 夜间线与白天线锁竞争 | 同一把 flock `-w`，慢则顺延（已验证模式）|
| 队列无锁读改写 | 生产行共持锁纪律不变；手跑必拿锁（runbook §4）|
| 四产物族范围膨胀 | 每族独立 mini-spec + 验收门，WP-5 内按族推进，不混包 |

## 7. 总量预估

Codex 执行 ~5-7 个工作日 + 每包审计。LLM 成本：backfill drain（已实测无恙）、③-C 增量（WP-0 钉死）、summaries/classification 增量+回填（WP-5 mini-spec 内核算）。终态 = §0 三闭环成立 + 闭环演习通过 + L3 地基前置条件就绪。
