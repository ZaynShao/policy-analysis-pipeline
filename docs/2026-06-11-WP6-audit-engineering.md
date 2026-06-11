# WP-6 工程面审计结论（Claude，2026-06-11 晚）

> 范围：6a 闭环巡检 + 6a-fix 时代分界 + 6b 部署 + 6c review_consumer 接线全链（5 次续跑）+ 6d 构建可重复性。
> 未含（待办）：6e 文档终态重写（OPERATIONS §8 + SCHEMA 清壳，排明晨首跑验证后）、Mac 退役、48h 演习（需用户排期）。

## 1. 过关审计：通过

- **6a/6a-fix 巡检器**：603 passed（独立复现），红 commit 真红；首次空跑即正确识别"非 VPS 作者动产物路径"（两条 6/6-6/7 历史 commit，假阳性→时代分界线 `PURITY_CUTOFF=2026-06-11` 修复，cutoff 后严格执法的回归测试在）。**6b 部署后我亲手跑 dry-run 全绿** `{"ok":true,"state_paths":6,"vault_product_commits":12}`，10:45 cron 在位。
- **6c review_consumer**（一波五折，全部按红线干净停）：①host 缺 psycopg2 → apt 装；②heng-pg 仅容器网络可解析 → cron 改容器形态（runbook 已注明原因）；③真 bug：`L1ReviewQueue.id` text NOT NULL 无默认值，B14 单测从未对过真实表 → 确定性 id（sha1(dedupeKey) 前 24 位，幂等）红绿修复（604 passed）；④镜像陈旧再跑仍 0/15（resume4 handoff 漏了重建步，**Claude 的交接缺陷**）→ ⑤重建+终验 **forward 15/15、PG 计数 15/15、reverse no-op**。cron 2 条在位（10:05 前送 / */30 8-22 拉回）。
- **6d 构建可重复性**：constraints.txt（39 行，源=已知好镜像 freeze）+ Dockerfile 层序（git→依赖层 `-c constraints`→COPY scripts→`--no-deps -e .`）。服务器 repro-test 四闸全过；**resume5 实战首验：重建命中依赖缓存零解析**——当日两次 pip 网络事故的根因关闭。

## 2. 阶段评估

- 可见闭环建成：巡检器（6 项活性 + vault 纯净 + sync errors）每日 10:45 自动体检，异常飞书、健康静默。"忘了上云"从回忆测验变为告警，roadmap 立项初衷兑现。
- 人工裁决回路：pool（实有 15 条 fetch_fail 积压，并非空）→ PG 队列 15 条待裁 → hengguan UI 可裁。**applier 推迟决策（roadmap #5）的触发条件已逼近**：用户裁掉第一条，就该按 B14-applier-handoff 建 applier。
- 服务器 crontab 终态 32 行（含 15 条 policy 产线/巡检/consumer 行）。

## 3. 洞察

1. **镜像陈旧是闭环盲区**：resume4 的 0/15 浪费一轮的根因=容器跑旧镜像而无人察觉。低成本堵法（排 6e 后小包）：构建时 `LABEL git_sha=<sha>` 烙进镜像，closure_audit 加一项"镜像 SHA vs src HEAD 漂移"检查。
2. **单测过≠契约对**：B14 的 build_upsert 单测验了 SQL 形状却没对过 Prisma 真实表（id 无默认值）。与 WP-4 的 analysis_context 断层同款教训：**跨系统消费前必须以对方实测 schema 为准对账一次**。
3. 五次续跑、五次按红线干净停、零不可逆损失——包结构（侦察先行/dry-run 先行/cron 最后装）+ 红线模板的复利在 6c 体现得最充分。

## 结论：WP-6 工程面关闭。余项：6e 文档终态（明晨首跑验证后）、镜像 SHA 巡检小包（可并入 6e）、Mac 退役 + 48h 演习（用户排期）。
