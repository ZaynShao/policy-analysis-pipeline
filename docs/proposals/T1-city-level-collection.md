---
title: T1 · 市级政策完整覆盖 · 设计稿
status: APPROVED — user 2026-05-19 reviewed,Q2/Q3 lock,进 writing-plans
proposed_by: 接手 session(2026-05-19)对 STATUS T1(P0)任务的设计响应
proposed_at: 2026-05-19
related_status_task: STATUS § 待办 · 优先级 P0 · T1
delivery_window: 2-3 天(本次只交付 P0 ~50 城实跑 + 准备能力)
---

# T1 · 市级政策完整覆盖 · 设计稿

## 背景

vault 现状:992 篇政策中市级仅 42 篇,覆盖 ~30 个地级市(全国共 ~330 个),且 region.code 大面积 NOCODE,部分城市同时有"有 code"和"无 code"两条 key。STATUS 旧值估"~10 重点城市",实测略好,但**完全不算全量**。

`scripts/l1_collect/` 当前只有 `.gitkeep`,市级采集脚本一行未写。OPERATIONS §1 总图给出了 Step 2-5 的形态,但每个 step 都还是 TODO。`vault/00 背景资料/渠道目录.md` 已有 552 行,含中央 13 部委(已验证)+ 地方 ~10 个已验证 + 31 省发改委候选 + 其他散点;但市级渠道远未完整。

刚做的 L2 关系网轻量精度试探(`state/probes/2026-05-18_relations_quick/`)发现:**L1 raw 已经混入新闻稿**("国际储能网"、"_市县" 标签、媒介转载等),被当政策入库后污染了下游派生。T1 新写采集脚本时必须把这道过滤纳入,而不是事后清理。

## 目标 / 非目标

### 目标(2-3 天交付)

1. 建立 ~330 个地级市的渠道清单(候选→联通验证→已扫三态),京沪津渝下辖 ~80 区单列
2. 用户拍板的"业务驱动 P0 ~50 城"优先级清单
3. `scripts/l1_collect/` 下完整的 Step 2-5 采集流水线脚本,内置"政策 vs 新闻稿"过滤
4. **P0 ~50 城实跑入库**,Schema 合规度 100%
5. P0 跑完**立即**做一轮质量评估,验收报告落 `state/probes/`
6. 为 P1(~80 区)/ P2(~200 城)备好执行能力(渠道联通测试 + 分批 trigger 脚本 + 触发条件文档)

### 非目标

- ❌ P1 / P2 本次不实跑,跑不跑下次决策
- ❌ 不重抓已入库的 992 篇政策(LESSONS A1 + STATUS §范围之外)
- ❌ 不抄 legacy 老采集脚本,所有脚本在 pipeline 仓**新写**
- ❌ 不在采集阶段做 LLM 业务判断(LESSONS B1 + OPERATIONS §1 注脚)
- ❌ 不让 pipeline 自动写 vault `00 背景资料/`(SCHEMA §1 写权约定)

## 关键决策记录(本次 brainstorming 已 lock)

| 决策 | 用户选择 |
|---|---|
| 优先级清单来源 | A · 主 session 用业务常识推 ~50 城,user 10 秒扫一遍调整 |
| 本次交付边界 | B · 渠道清单 + 脚本骨架 + P0 ~50 城实跑入库 |
| 跑完后动作 | 立即评估质量,然后准备 C(P1/P2 执行能力) |
| 架构方案 | 3 · Hybrid(pipeline 存机器消费清单,vault 反哺为人工 review 后合并) |

## 架构选型(方案 3 Hybrid)

| 层 | 位置 | 谁写 | 谁读 |
|---|---|---|---|
| 机器消费的扫描清单(候选/验证/已扫三态) | `pipeline/state/T1_channels/` | pipeline 采集脚本 | pipeline 采集脚本 |
| 人工 canonical 渠道目录 | `vault/00 背景资料/渠道目录.md` | 仅人工(含主 session 作为 review 后的"人工写者") | pipeline 启动时只读 |
| 反哺动作 | 主 session 生成 markdown 片段 → review → 合并到 vault canonical | 主 session 协助 + 用户最终 ack | — |

理由(对应 LESSONS):
- **C1** 工程层与数据层物理分离:机器扫描状态属工程中间产物
- **C2** Staging 不进数据仓:候选/状态数据留 pipeline state
- **A4** 边界例外要白名单化:vault canonical 由人工守门,不放 pipeline 自动写
- **SCHEMA §1** 写权约定:`00 背景资料/` pipeline 写权 ✗,人工写 ✓

## 数据结构

### `state/T1_channels/channel_catalog.yaml`

每条渠道一项:

```yaml
- city: 杭州市
  province: 浙江省
  level: 市             # 市 / 区(京沪津渝下辖)
  city_code: '330100'   # 国标行政区划代码(6位)
  channel_type: 发改委    # 主线三种:发改委 / 能源局 / 政府网;按需扩展:经信委 / 商务局(消费品以旧换新等)
  root_domain: fgw.hangzhou.gov.cn
  list_url: https://fgw.hangzhou.gov.cn/col/col1229453592/index.html  # 政策列表页
  source: vault_catalog | llm_generated | manual
  status: 候选 | 验证 | 已扫     # 候选=未测联通;验证=联通且页面结构对;已扫=至少跑过 1 次 Step 2
  last_probed_at: '2026-05-19T...'
  probe_result: ok | http_error | structure_unknown | empty
  notes: ''
```

### `state/T1_channels/city_priority.yaml`

```yaml
version: 2026-05-19
batches:
  P0:  # ~50 城,本次实跑
    - city: 北京市
      city_code: '110100'
      reasons: [充电_一线, 加油_top, 电力_直辖市]
      priority_score: 9.5
    # ...
  P1:  # ~80 区,准备
    - city: 北京市朝阳区
      parent: 北京市
      city_code: '110105'
    # ...
  P2:  # ~200 城,准备
    - city: 南通市
      city_code: '320600'
      reasons: [汽油消费_top50]
```

### `state/T1_channels/channel_probe_log.jsonl`

每次联通性测试一行,机读 + 可重放:

```json
{"timestamp": "...", "root_domain": "fgw.hangzhou.gov.cn", "http_status": 200, "page_has_list_pattern": true, "verdict": "ok"}
```

## 采集流程(`scripts/l1_collect/`)

按 OPERATIONS §1 总图,一次性写完 Step 2-5 五步:

```
Step 2 · 渠道扫描       run_step2_scan.py
  输入:channel_catalog status=验证 的渠道
  动作:翻页爬列表页,提取 (标题, URL, 发布日期-粗) 三元组
  输出:state/T1_scan_raw/<batch>_<city>.jsonl
  参数:OPERATIONS §4 — 时间窗 24h(本次首跑放宽到 36 月)/ 翻页硬上限 5 页 / 连续 3 页 <10% 新增停

Step 3 · 标题过滤 + 查重     run_step3_filter.py
  输入:Step 2 输出 + vault 0_raw 全量索引(用于查重)
  动作 a:能源主题词过滤(电力/油气/充电/储能/新能源/双碳/输变电/电网...)
  动作 b:⚠新闻稿过滤(本任务新增,详见下节)
  动作 c:三维查重 URL+文号+标题哈希(LESSONS B2),归一化规则与现有 raw 一致
  输出:state/T1_candidate/<batch>.jsonl

Step 4 · 抓取正文       run_step4_fetch.py
  输入:Step 3 candidate
  动作:按 OPERATIONS §5 兜底链路 Firecrawl→Tavily→trafilatura→BeautifulSoup
  输出:state/T1_fetched/<pid_provisional>.md(含 raw HTML 抓取的 body)
  并发:控制在 5 路,避免被封;失败重试 2 次后标 fetch_error

Step 4.5 · 元数据抽取     run_step4_5_extract.py
  输入:Step 4 fetched
  动作:确定性提取(title/official_number/date/issuer/region),全部 regex + canonical lookup
  ⚠ 严禁 LLM 业务判断(LESSONS B1)
  输出:state/T1_extracted/<pid_provisional>.yaml(含 frontmatter 候选)

Step 5 · L1 入库         run_step5_ingest.py
  输入:Step 4.5 extracted
  动作:按 SCHEMA §2 frontmatter 白名单生成最终 yaml + body 段(只 ## 政策原文)
        过 validate_schema.py 校验通过 → 写 vault/0_raw/policies/<filename>.md
  输出:vault 写入 + state/last_run.json + state/T1_ingest_log/<batch>.jsonl
```

总入口:`scripts/l1_collect/run_pipeline.py --batch P0`,串行调度上述 5 步,支持 `--resume` 断点。

## 新闻稿过滤(本任务新增)

放在 Step 3 内。规则全确定性,不上 LLM:

1. **域名黑名单**:`gjcwx.com`(国际储能网)/ `xinhuanet.com` 等媒体域名 / `xinyongxx.gov.cn` 转载站
2. **标题特征**:含 "_市县" 后缀(自动从 sitemap 抓时常见误归)/ "[XX 网]" 前缀
3. **issuer 检验**:Step 4.5 抽出的 issuer 必须是政府机关或直属事业单位(canonical 表 lookup);失败标 `issuer_unknown`,**不入库**留 state/T1_quarantine/
4. ~~白名单 override~~:**本阶段不开**。政府网"政策解读"页若被规则误杀,接受。理由:user 选择"清爽,接受被误杀"(2026-05-19 ack)。Quarantine 留全量,后续如果误杀率高再考虑加 override

输出:`state/T1_quarantine/<batch>.jsonl` 记录被过滤项 + 原因,可手工 review

预计过滤率:P0 阶段 5-15%(参考 L2 试探观察)

## 优先级机制(P0 ≈ 50 城 union)

主 session 推算口径:

| 业务线 | 选城规则 | 估算城数 |
|---|---|---|
| 充电业务 | 一线 4 + 新一线 15(成都/长沙/郑州/西安/济南/合肥/昆明/无锡/宁波/青岛/厦门/天津/苏州/福州/沈阳)| 19 |
| 加油业务 | 汽油消费 Top 50(与上面去重,净增 ~10 二三线高消费如东莞/佛山/嘉兴/温州/泉州/南通/烟台/潍坊/常州/惠州) | 净 ~10 |
| 电力业务 | 27 省会(去掉已在上述列表的) + 5 计划单列市(深宁青夏厦) | 净 ~20 |
| **去重 union** | | **~50** |

加权分:每个城市每命中一个业务线 +3 分,直辖市 +2 分,GDP Top 10 +1 分。最终 priority_score 排序,前 50 进 P0。

清单生成由 `scripts/_oneshot/t1_build_p0_city_list.py` 输出到 `city_priority.yaml`,用户 10 秒扫一眼可调。

## P0 跑完后的质量评估(本次必做)

参考 L2 试探的 oneshot 模式 — 抽样脚本 + 主 session 手判,产物落 `state/probes/2026-XX-XX_T1_P0_quality/`:

| 维度 | 抽样方法 | 通过线 |
|---|---|---|
| 渠道有效性 | 每城抽 1 条入库政策,看 URL 真访问到该市政府网 | ≥90% |
| 标题相关性 | 入库政策抽 20-30 条,看能源主题相关性 | ≥90% |
| 新闻稿污染率 | 全 P0 入库扫一遍特征 | ≤5% |
| Schema 合规 | `validate_schema.py` 严格违反 | 0 |
| 入库数量 | 50 城实际入库总数 | 报告即可(估 200-500 篇)|
| issuer/region 准确率 | 抽 20-30 条,看 issuer 字段与渠道域名匹配 | ≥95% |
| 重复入库率 | Step 3 三维查重命中数 / 总抽数 | 报告即可 |

通过线**全部达标** → 进"准备 C"。任一不达标 → 修对应模块,**不进 C**。

## 准备 C 的执行能力(本次必做,不实跑)

- P1 / P2 城市的渠道候选**全部跑一遍联通性测试**,channel_catalog 标好状态
- 提供分批 trigger:`run_pipeline.py --batch P1` / `--batch P2` / `--cities 城A,城B` / `--channel 单域名`
- 文档 `state/T1_channels/README.md` 说明:
  - 渠道无法联通的城市清单(无源)
  - 渠道返回结构无法解析的城市清单(需人工写 parser)
  - 推荐的分批节奏(并发上限 / cron 触发条件)

跑不跑、什么时候跑 → 下一次决策。

## 反哺 vault 渠道目录

P0 跑完后:

1. 主 session 从 channel_catalog 抽出 `status=已扫 且 ingest_count >= 1` 的渠道
2. 按 vault `渠道目录.md` 现有 markdown 格式生成片段
3. 主 session 提交给用户 review(diff 视图)
4. 用户 ack 后,**主 session 在用户监督下写入** vault canonical(2026-05-19 user 选择,Open Q2 lock)。每次写前给 diff 视图,用户回 "ok" 才动笔
5. SCHEMA 约束:pipeline 脚本**永远**不自动写 `00 背景资料/`

## 验收标准

| 验收项 | 通过条件 |
|---|---|
| 渠道清单 | channel_catalog.yaml ≥330 城候选 + ≥100 城联通验证通过(P0+P1+部分 P2)|
| 优先级清单 | city_priority.yaml 含 P0/P1/P2 三档,user ack |
| 采集脚本 | `scripts/l1_collect/` 含 Step 2-5 + run_pipeline.py,可 `--resume`,有 dry-run |
| P0 实跑 | ~50 城至少 80% 跑到 Step 5 入库,Schema 合规 100% |
| 质量评估 | `state/probes/2026-XX-XX_T1_P0_quality/verdict.md` 出具,7 个维度全部达通过线 |
| 准备 C | P1/P2 渠道联通已测,分批 trigger 脚本可用 |
| 反哺 vault | 用户 ack 的 markdown 片段已合并到 `渠道目录.md` |
| 不污染 | vault `00 背景资料/` 无 pipeline 写入痕迹,vault `0_raw/policies/` 增量篇数与 ingest_log 一致 |

## 涉及的 LESSONS / SCHEMA 边界

- **LESSONS A1** Raw 不可变:Step 5 入库一次写完,不就地编辑
- **LESSONS B1** 元数据抽取不做语义判断:Step 4.5 全 regex + canonical lookup
- **LESSONS B2** 查重三维:Step 3 实现 URL+文号+标题
- **LESSONS B3** 抓取兜底链路:Step 4 实现 Firecrawl→Tavily→trafilatura→BS4
- **LESSONS B6** 模糊匹配先校验:渠道候选先联通测试再用
- **LESSONS C1+C2** 工程/数据分离:T1_channels 留 pipeline state
- **LESSONS C3** Oneshot 跑完归档:t1_build_p0_city_list.py 跑完即标
- **LESSONS C5** 数字脚本生成:覆盖率/入库数全部从 dump_status.py 自动算
- **LESSONS C7** 脚本必须正式归档:不允许 `/tmp/` 引用
- **LESSONS D5** Subagent 只跑独立任务:本任务主 session 串行,渠道扫描可考虑 subagent 并行(只读+产数据,符合 D5)
- **SCHEMA §0/§2** Raw immutable + frontmatter 白名单:Step 5 严格遵守
- **SCHEMA §1 写权约定**:pipeline 不写 `00 背景资料/`,反哺走人工 review
- **SCHEMA §F drift**:新入库的市级政策严禁带 legacy drift 字段(tags / classification / 嵌套 provenance / 等)

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| LLM 生成的市级渠道域名幻觉 | 联通性测试 gate,失败的不进 catalog status=验证 |
| 政府网反爬/封 IP | 并发 5 路 + UA 轮换 + 失败退避;严重时人工 review |
| 政策列表页结构千差万别 | 写通用 parser + per-city override hook;无法解析的城市标 `structure_unknown` 留 state |
| 新闻稿过滤误杀政府解读页 | 白名单 override 政府解读 URL pattern;quarantine 留全量供 review |
| 时间预算溢出(2-3 天) | 优先保证渠道清单 + 优先级 + 脚本骨架(交付边界 A 的最小集),P0 实跑可缩到 30 城兜底 |
| P0 跑完发现 L2 流水线对新数据炸 | 不在 T1 范围内修,记 backlog 给 T4/T5 |
| 反哺渠道目录引入与现有手工内容的格式差异 | review 时主 session diff 模式呈现,按现有格式适配 |

## 时间预算

| 阶段 | 估时 |
|---|---|
| 渠道候选 LLM 生成 + 联通性测试脚本 | 0.5 天 |
| city_priority.yaml 主 session 推算 + 用户 ack | 0.1 天 |
| Step 2-5 + 新闻稿过滤代码 | 1 天 |
| P0 实跑(50 城,含 fetch/retry)| 0.5-1 天 |
| 质量评估 + 反哺 markdown 生成 | 0.3 天 |
| P1/P2 准备(联通测试 + trigger 脚本)| 0.2 天 |
| **总计** | **2.6-3.1 天** |

超 3 天 → 缩减 P0 到 30 城兜底,保 6 个验收项核心。

## Open questions

1. **未决** — P0 city 清单具体哪 50 城,主 session 推完后会让 user 扫一眼。如果有"必须包含"或"必须剔除"的城市,本次可一并 ack
2. **已 lock(2026-05-19)** — 反哺 vault:主 session 在 user 监督下写入,每次写前给 diff 视图,user ack 才动笔
3. **已 lock(2026-05-19)** — 新闻稿过滤白名单 override **不开**,清爽规则,接受被误杀;quarantine 留全量供事后 review
