# L1 采集修复 — 设计 spec

**日期**: 2026-06-06
**分支**: `feat/l1-capture-repair`（worktree `~/dev/政策分析-pipeline-l1-repair`，off main `ab2d542`）
**前序**: L1 体检报告 `docs/reviews/2026-06-06-L1-capture-quality-assessment.html`

## 1. 目标与边界

把 L1 采集层从"牢靠但不完整"升级为"全面 + 质量门控 + 可定期审计"，**填上决策层需要的全国态势**。采集范围 = **决策 A**：国家级 + 全省 31（含直辖市全量）+ 重点城市 48（`scripts/l1_collect/city_priority.py`）。SOP 的"地市 330 全覆盖"目标**下调对齐**到此口径（说实话，330 全县市 = 过度采集）。

### 1.1 与 service 线（`feat/service-deploy`）的边界 — 钉死防撞

| | 本线 = **采集方法** | service 线 = **频率编排 + L2 派生** |
|---|---|---|
| 职责 | 发现渠道→扫→质量门→重抓→入库**新 raw**→覆盖审计 | 拿 vault 现成 raw → `hash_ledger` 增量派生 L2 → sync Postgres |
| 触发 | 本 session 手动 + 将来 service 调度调用 | cron / 手动 |

**接缝两点**（实测确认零重复）：
1. 本线只 **append** `vault 0_raw/policies/`；service 的 `hash_ledger`（content-hash + pipeline_version）检测到新文件 → 标 `needs_rebuild` → 派生。
2. 本线 `run_incremental` **复用** service 已建的 `scripts/service/`（`l1_status` 运行锁），防采集与派生并发撞车。

service 线的 `hash_ledger`/`orchestrate` 全是 **L2 派生**增量，**不采集**（README 实证 + memory "L1采集优化未启动"）。故无功能重叠。

## 2. 根因诊断（实测证据，非体检报告的推断）

实测 3 个列表页（`requests` + BS4，现有机制）：

| 列表页 | 结果 | 含义 |
|--------|------|------|
| 国务院政策库 | **HTTP 403** | 反爬挡住，BS4 拿到空壳 31 字 |
| 国家能源局（旧写死 URL） | **HTTP 404** | URL 已失效 — 写死 URL 当天就烂 |
| 广东发改委 | 200 / 204 链接 / ~10 带日期 | 能用，但指向**首页**非政策列表页 |

**结论**：大省/国家级盲区的根因 = **采集机制三重失效**，非简单"没采"：
1. 国家级母文件页**反爬（403）或 URL 失效（404）** → 纯 BS4 + 写死 URL 采不到。
2. 就算能连，渠道指向**根域名/首页**而非政策列表页。
3. **JS 渲染** + **翻页假设错**（`?page=N`，实际多用 `index_N.html`）压低召回。

**资产**：vault `_meta/channel_registry.yaml` 164 条**已带 level 分级**（国家 24 / 省 50 / 市 62 / 区 19 / 县 9），是渠道发现的好种子（但只是发文域名，需发现列表页路径）。

**薄文件实况**：873 篇中 **164 篇 body <800 字**（非体检报告说的 ~18），且混三类——① 真被截断的政策（武汉充电办法 250 字 / 宁夏现货方案 286 字 / 四川储能导则 310 字）；② 本就短的合法条目（青海电量月报）；③ 非政策残渣（解读 / 一图读懂 / 建言）。**故重抓必须排在质量门之后**，只重抓「确认是政策 AND 被截断」那批。

## 3. 模块结构（`scripts/l1_collect/`）

```
channel_discovery.py   新建  渠道发现:registry+决策A目标 → Tavily搜 → LLM选列表页URL → probe验证
step2_scan.py          修改  分层兜底扫描:BS4→firecrawl;真翻页;召回偏向(拓关键词)
fetcher.py             修改  firecrawl v0→v1;MIN_BODY_LEN 200→500
policy_gate.py         新建  采集时质量门:heuristic→LLM judge(复用l1_audit/news_classifier模式)
pdf_refetch.py         新建  重抓(排在门之后);单调只增护栏
run_incremental.py     新建  方法本体:run(config)→summary,纯函数,l1_status锁,--since,--level
audit_coverage.py      新建  省×主题矩阵+零覆盖告警+新鲜度+缺口归因+HTML
common_llm_client.py   新建  从env构建judge client(deepseek-flash),无env返None
```

### 3.1 `channel_discovery.py` — 渠道发现（治 403/404/写死 URL 烂）

**输入**：决策 A 目标表 = ① 国家级 13 核心机构（发改委/能源局/工信部/商务部/国务院/财政部/住建部/市监总局/交通运输部/生态环境部/标准委/央行/税务总局）× 适配业务线；② registry 中 `region.level ∈ {国家,省}` 的域名；③ 省级 31 缺口补齐。

**流程**（每个目标）：
1. **Tavily 搜索**：`{机构名} 政策文件 通知 列表` → 候选 URL 集。
2. **LLM 选真列表页**：deepseek-flash 判断哪个候选是"政策文件列表页"（非首页/非具体文章/非检索页）。prompt 输出 `{list_url, confidence, reason}`。
3. **probe 验证**：复用 `connectivity_probe.probe_url` → verdict=ok（含列表特征）才升 `status=验证`。403/404/空 → 标 `候选` + 记 verdict，**留待 firecrawl 渲染兜底**（scan 阶段处理）。

**输出**：写 `state/T1_channels/channel_catalog.yaml`（追加国家+省级，已有 `root_domain` 跳过，幂等）。

**LLM 边界**：这里用 LLM 做**发现/判断**（哪个 URL 是列表页），符合"LLM 管判断、正则管结构化抽取"的原则线。

### 3.2 `step2_scan.py` — 分层兜底扫描（改造）

现状问题：① 纯 BS4，JS/反爬页拿空；② `?page=N` 翻页假设错；③ KEYWORDS 有召回漏词。

改造：
1. **分层抓列表页 HTML**（镜像现有 `fetcher.py` 三级模式）：BS4 免费先试 → 若 `text<阈值` 或 `links=0` 或 HTTP≥400 → **firecrawl v1 渲染兜底**（穿透反爬/JS）。只在 BS4 失败时才花 firecrawl（省钱）。
2. **真翻页**：尝试 `index.html` / `index_2.html` / `index_3.html` 等常见政府站模式（不止 `?page=`）；保留 `MAX_PAGES` + 新增比阈值早停。
3. **召回偏向**：KEYWORDS 拓词补漏 —— 加 `换电`、`现货市场`、`绿证`、`绿电`、`车网互动`、`V2G`、`配电网`、`分布式`、`加氢`、`抽水蓄能`、`需求侧`。关键词仍**正向 scoping 到三业务线**（这是对的，语料就只要加油/充电/电力），但补全漏词。精度由下游 `policy_gate` 兜。

**原则**：scan 阶段**召回优先**（宁可多扫），**精度交质量门**（L2 模式：宽进 → 末端门控）。

### 3.3 `fetcher.py` — firecrawl 升级（改造）

- `https://api.firecrawl.dev/v0/scrape` → `v1/scrape`。
- `MIN_BODY_LEN` 200 → 500（200 挡不住门户壳/PDF 壳）。
- key 从 env `FIRECRAWL_API_KEY` 读（已落 models.env，out-of-git）。

### 3.4 `policy_gate.py` — 采集时质量门（L2 模式）

**复用** `scripts/l1_audit/news_classifier.py` 的成熟模式（heuristic 预筛 → LLM 确认），搬到**采集时 inline**（入库前，rejected 永不成 raw → 干净）。

**两段**：
- **Stage 1（程序门，便宜）**：URL 域名黑名单 + 政策标题信号（通知/意见/办法…）+ gov 域名 + 正文信号（根据/现就…）→ 明显政策**直通**、明显非政策（媒体黑名单）**快拒**。
- **Stage 2（LLM judge）**：灰区 → deepseek-flash 打标 `{label: policy|non_policy_index|non_policy_news|non_policy_reply, confidence, evidence}`。

**输出 `GateResult`**：`action ∈ {pass, reject, review_queue}`。`confidence<0.7` → `review_queue`（人工复核，不静默丢）。

**reject 桶走 quarantine 隔离、不物理删除**（TODO-B：误抓进来的行业情报将来能从隔离区捞）。

**golden 校准**（你第 3 点，镜像 ②-B/③-C）：
- golden ~50 篇 = 好政策 25（vault 抽 body 长的）+ 非政策 25（`b7_contamination.jsonl` 已知 65 条抽）。
- 埋 10 个 planted（5 好政策谎称非政策 + 5 坏文档谎称政策）。
- **校准门：planted-recall ≥ 0.9 才上岗**。不达标 → 调 prompt 重跑（≤4 次）。
- 校准报告 `state/l1_gate/gate_calibration.json`。

### 3.5 `pdf_refetch.py` — 母文件重抓（排在门之后）

**候选** = `should_refetch(file)` = `body字数 < 800 AND gate判定=政策`（**谓词，非 pid 清单**）。

**抓取**：`pdfplumber`（直接下 PDF URL 提取）→ `firecrawl v1`（渲染兜底）。

**单调只增护栏（写回 raw 的红线）**：只在**新捕获严格更长 AND 来自同一 `source_url`** 时才写回 `0_raw/*.md` 的 body 段；`新≤旧` 或源不同 → **跳过 + 记日志，永不缩短/替换**。frontmatter 不动，记 provenance（`refetched_at` / `old_chars` / `new_chars` / `via`）。

**§C 合规论证**：确定性 fetch（无 LLM 判定）+ 单调只增 + 谓词候选 + 幂等（已完整→no-op）→ 属"采集补全"，对齐 §C v1.1（确定性重算可就地写 raw + provenance），不违"LLM 判定不写 raw"。详见 §7 纪律审计。

### 3.6 `run_incremental.py` — 方法本体（service 线调用入口）

**纯函数契约**：`run_incremental(config) -> summary`。无调度逻辑（频率由 service 线编排）。append-only。

参数：`--level national,province,city`（子集）、`--since YYYY-MM-DD`（跳过早于此的列表项）、`--dry-run`。

**流程**（每渠道）：`l1_status` 取锁 → Step2 分层扫 → Step3 规则过滤 → Step4 抓全文 → **policy_gate 质量门** → Step5 入库 vault → 释放锁。

**与 service 的接口**：写新 raw 文件即接口；取 `l1_status` 锁即并发协调。summary 返回 `{channels_run, scanned, gate_passed, gate_rejected, ingested}`。

### 3.7 `audit_coverage.py` — 覆盖审计（定期，你第 5 点）

**指标 LLM 设计一次 → 固化为规则**（不每次调 LLM，防漂移）：
- **M1 省×主题矩阵**：充电/加油/电力 各省政策数（读 `_meta/business_view/*.yaml` 的 region+themes）。
- **M2 零覆盖告警**：重点省 × 核心主题 = 0 → HIGH。**一条硬规则 = 你说的"政策大省某类政策不应为 0/很少"**。
- **M3 新鲜度**：各省最后采集日期，>60 天 → WARN。
- **M4 内容质量**：各省政策平均 body 字数，<1000 → 预警。
- **M5 渠道健康**：各省验证/候选渠道数。

**缺口归因（反馈环，memory B7）**：每个零覆盖告警 emit **候选归因** —— 是「采集缺口」（该省该渠道扫描数=0 → 补采）还是「归属错标」（采到了但 region/theme 标错 → 回灌 ②）。输出 HTML 报告 + 可执行的补采目标清单。

## 4. 执行序（一站到底，中间一个 checkpoint）

```
阶段1 建方法(TDD): channel_discovery → scan改造 → fetcher升级 → policy_gate(+golden校准) 
                    → pdf_refetch → run_incremental → audit_coverage
阶段2 小切片验证: 国家13 + 大省(江苏/浙江/四川)几渠道, 端到端真跑
                  + gate golden 校准达标(planted-recall≥0.9)
                  + 渠道发现质量抽查(发现的 list_url 对不对)
阶段3 【CHECKPOINT — 用户审】: 发现质量样本 + 召回样本 + gate 精度
阶段4 全量 backfill(孤儿化 nohup): 国家+省31+重点48 全渠道
阶段5 收口: 覆盖审计前后对比 + 退~43非政策残渣(走quarantine) + commit两仓(vault raw + pipeline)
            + 八步采集法 doc 标注"重生为纯L1 SOP, 见 run_incremental"
```

**孤儿化**：长抓任务 `nohup caffeinate -i <cmd> >log 2>&1 & disown`（harness 后台 ~20min 被回收 + Mac 睡眠冻杀）。

## 5. 正则 vs LLM 的原则线（你第 2 点）

**LLM 管判断/发现** · **正则管结构化抽取**：
- LLM：渠道列表页 URL 发现（治写死 URL 烂）、政策 vs 非政策判定（质量门精度）。
- 正则：文号〔〕/日期/issuer 域名查表（政府公文高度规整，正则可靠且确定性）。
- **metadata 保持正则不上 LLM**：issuer 缺失由下游 ②-A 确定性 resolver 兜；盲目全换 LLM 引入非确定性 + 成本无收益。

## 6. Deferred / 不在本线（用户 2026-06-06 锁定）

| TODO | 内容 | 触发 | 挂靠 |
|------|------|------|------|
| **A 微信公众号政策评论** | commentary 源，RSS 抓取、自动化有问题 | **政策采集跑完之后** | memory B3（commentary 迁移） |
| **B 零散行业情报** | 不建专门抓取器；只收政策采集时误抓漏进来的（低优先级） | 被动；gate reject 桶走 quarantine 保住误抓项 | memory B1（市场行情第三源） |

## 7. 纪律审计（零补丁承诺 + 滑坡自审）

- **采集 = append-only**（纪律A）：新文件追加，不改已有。
- **重抓写回 raw**：唯一碰 immutable raw 处。审计通过 —— 谓词候选（非 pid 清单）/ 确定性 fetch（非 LLM）/ 单调只增（永不缩短或换源）/ 幂等（已完整 no-op）/ provenance 记录。优化的是**全局不变量「raw body=源的完整捕获」**，非针对特定文件的补丁。对齐 §C v1.1。
- **LLM 判定不写 raw**（§C）：gate 的 LLM 判定决定 pass/reject（入库前，不写 raw）；channel discovery 的 LLM 判定写的是 `channel_catalog.yaml`（派生层，非 raw）。
- **gate reject 不物理删**：走 quarantine（不删非自己创建的内容 + 保住误抓情报）。

## 8. Tavily / firecrawl 预算

- firecrawl：**只在 BS4 失败时兜底**（scan + refetch），省钱。
- Tavily：渠道发现，~150 目标 × 几次搜索，一次性。
- 两 key 已落 `~/.config/policy-pipeline/models.env`（out-of-git，勿提交/勿写摘要）。

## 9. 验收清单

- 全测试绿（`pytest tests/l1_collect/`）。
- 渠道健康：国家 ≥8、省 ≥20、市 ≥48（验证态）。
- gate 校准：planted-recall ≥ 0.9。
- 增量 dry-run 无报错。
- 覆盖审计可跑，江浙川充电覆盖从 0 → 非 0（backfill 后）。
- 重抓单调只增护栏生效（无 raw 被缩短）。
