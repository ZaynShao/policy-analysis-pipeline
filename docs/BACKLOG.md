# 项目 Backlog · 推后的设计节点

> 这里登记"已认可、但有意推后"的工作,避免 deferred → 被遗忘。每条带**触发条件**(什么时候该捡起来)。

---

## B1 · 市场行情(market_intel)第三源 — 推后

**状态**:已认可方向,**轻量承认**(审计里标 `market_intel` 不 archive),**完整建设推后**。决策见 2026-05-30 对话。

**是什么**:在 `政策(policies)` / `评论(commentaries)` 之外,引入第三种源类型——**市场行情/业务需求情报**:政府公示/公告里的项目清单、竞配结果、补贴清单、可开放容量、调价,以及项目并网/落地等市场动态。它既不是政策方向(policy),也不是行业观点(commentary),而是"哪里有什么业务需求"的地面信号——对滴滴三块业务(电力/充电/加油)最可执行的情报。

**为什么推后(B 面)**:
1. 分类法要从 2 类扩到 4 类(policy/commentary/market_intel/真噪声),classifier+schema+归属层都要扩。
2. 市场行情更像**带时间戳的数据流**(快照会快速过期),不是稳定文档库——可能需要更结构化/时序的表示,是独立子设计,不是"再开个文件夹"。
3. **采集源问题**:目前这些是从 in-en 等行业镜像漏进来的,不是系统采集;真做要有专属采集策略(哪些源、什么频率)。
4. 和 commentary 的边界要划清("行情数据" vs "行情分析")。
5. 时机:引入它会成为一条新设计线,在 ①源到位 期间插入有 scope-creep / 推倒重来风险。

**轻量承认(现在就做的)**:L1 审计把这类 doc 标 `market_intel`,**保留不 archive、也不混进 policy**,先圈起来不丢。

**触发条件(什么时候捡起)**:
- ①源到位 + ②归属 + ③分析 稳定之后;**或**
- 用户为某个具体业务决策需要"市场需求/业务机会"情报时(如充电场站选址、储能项目机会、加油价格情报)。

**捡起时的第一步**:决定市场行情的表示(文档 vs 时序结构化)+ 采集源清单,再走 spec→plan→build。

---

## B2 · ②归属必须消费「2b 归属台账」 — 推后到 ②(强约束)

**状态**:① 阶段(2b)用 LLM 判出了 ~115 篇 policy 的**真实 issuer / region**,但按 SCHEMA §C(LLM 判定不写 raw,落派生层),**未写回 raw**,raw 的 id 一个没动(仍是 GO/SC 前缀)。判定结果存为台账。

**台账在哪**:`state/source_ready/go_sc_review/phase2_2b_decisions.json` 的 `remint` 段(115 条:pid + true_issuer + true_region + suggested_issuer_short);运行 2b 安全子集时另落 `state/source_ready/attribution_ledger_2b.jsonl`。

**为什么不能忘**:raw 里这 115 篇的发文机关/地区是错的(GO 万能前缀)。②归属若不消费这份台账,会照着错的 issuer/region 建关系→又一地孤岛(正是最初的痛)。

**触发条件**:②归属 一开工。

**捡起时的第一步**:② 的 spec **把此台账列为必需输入**,done-gate 写明"每篇 policy 的 issuer/region 依台账落实";若要顺带把 raw 的 id 也修正,**必须用确定性查表**(文号前缀 + gov 域名 → issuer_short/region),§C 合规,不可用 LLM 自由值。

## B3 · commentary reclassify(误入 policies 的解读/学习文章) — 推后

**是什么**:4 篇本质是**政策解读 / 学习文章**(非规范性政策)被收进了 `0_raw/policies/`,应迁 `commentaries/`:
- `P_2025_OTHER94DD_0718bc02`(习近平经济思想研究中心 学习文章,2a 发现)
- `P_2024_GO_6258c339`(安徽新型储能实施方案【文字解读】)
- `P_2024_GO_ecd2931e`(济南市中区 设备更新方案【政策解读】)
- `P_2025_GO_87ca9043`(广州花都 新能源十条【音频解读】)

**为什么推后**:跨语料 reclassify(评论 id 体系不同 + `_migrated_from` 标记),不在 ① 范围。

**触发条件**:② 或专门 cleanup pass。

## B4 · 残留 date 损坏 P_2027 — 推后到确定性身份字段修正

**是什么**:`P_2027_GO_572b0ea8`(《电力现货市场基本规则(试行)》)正文是 2023 年 9 月,date/id 年份被错成 2027。(另一例 `P_2048_..._4c4555f6` 已在 2b 作为重复迁 `_duplicates`,无需单列。)

**为什么推后**:date 修正应走 §C 确定性方法(`body_chinese_date`),与 ② 的确定性身份字段修正子步一起做,不在本次安全子集。

**触发条件**:② 确定性身份字段修正子步。

**②-A 进展(2026-05-31)**:resolver 跑到 P_2027 时——id 前缀修了(GO→真机关),但 **`body_chinese_date` 落款规则抽不到正文 2023-09 日期(可能不在文末落款格式)→ date 入 ②-A 待裁决队列,年份仍 2027**。`P_1900_SX_caf8e7eb` 同样(date 空+落款抽不到)。**B4 仍开**:需更强的正文 date 抽取(非仅落款)或手工。队列见 `state/source_ready/2a_review_queue.jsonl`(reason=date破损且落款抽不到)。

## B5 · 词表(registry)4 处小不自洽 — 推后到 ②(theme 匹配设计时定)

**是什么**:子项 b 的 lint(`scripts/l1_audit/vocab_check.py`)扫 themes_registry + entities/registry,registry 95% 自洽,余 4 处是 **theme 分类法判断**,交 ② 定:
1. **2 处真 alias 冲突(同词→2 个 theme)**:`负荷聚合`→{aggregator_access, vpp_theme};`成品油零售`→{gas_station_transition_theme, petroleum_retail_compliance}。需定哪个 theme 拥有该词。
2. **3 个 theme 的 entity 未标 type=theme**:charging_infra / power_market / v2g(entity 存在但 type 只有 concept)。按 registry 自己的规则应补 theme 类型。
3. **1 个反向**:`rural_revitalization_theme`(type=theme entity)不在 themes_registry。需定乡村是否为分析 theme(背景文件说乡村=关注方向非业务线)。
- 结构性重叠(虚拟电厂/新型储能/设备更新 = concept+其theme 共享词)**非冲突**,lint 已正确排除。

**为什么推后**:都是 theme 分类法决策,② 建主题匹配时一并定最自然,现在孤立改 shared 词表是过早判断。报告:`state/source_ready/vocab_check.md`。

**触发条件**:②归属 建 theme 匹配时。

## B6 · L1 采集覆盖补齐(真覆盖)— 强约束,易被当成"已完成"而漏

**是什么**:corpus 不是全量。政策 4 月中 bulk 了一波,**之后无增量补**。这是 L1「采集」轨——四节点的**上游/并行**,不是 ②/③/④。

**为什么不能忘(易漏点)**:① 收口收的是"清洗 935 快照"(去重/归档),**≠ 采集齐全**。charter §6 明确要"真覆盖:重点城市批量做完 + 尾部 backlog by小时/天持续补,**必须做完**";纪律A=采集只追加。但 B1–B5 没这条,极易被"① 已收口"误判为完成。

**和 ②-A 的关系**:②-A 是常驻确定性 resolver(非一次性),新采的政策走同一套自动清身份;新域名时扩 `_meta/channel_registry.yaml` 即可。故采集轨可排 ②-A 之后、复用之。

**子项 B6.1 · ingestion 做成 2线可操作**(用户延伸问题1):把采集+入库做成"runbook 可操作 + 确定性闸门"的流水线,使**模型档位不影响正确性**。确定性步(resolver/去重/validator)无需 LLM;需判断步(分类/域名curate/语义)配紧提示词+验收闸门。**路径:强模型先端到端跑一遍硬化 → 再配 2线模型按手册跑,闸门兜底。**

**触发条件**:②-A 收口后(算力/资源就绪)/ 或某区域覆盖被决策需要时。**捡起第一步**:盘点目标城市清单 + 现有 `scripts/l1_collect/` 能力,定批量+尾部节奏,先我跑一遍硬化。

## B7 · 覆盖盲区审计反馈环(AI发现→AI调整)— 升级 report §7 为闭环

**是什么**:framework `report_blueprint.yaml §7` 已有"缺口/盲区警示:主题×31省覆盖表 + 持续盲区",但只是**报告里一段**。用户要升级为**反馈环**:发现盲区(如江浙这类政策密集省在热门主题上为空)→ 自动调整。

**关键判别(否则误修)**:盲区两种根因、处置相反——**(a) 采集缺口**(确实没采到 → 触发定向采集,回 L1 轨)vs **(b) 归属错标**(在库但 theme/region 标错 → ② 的 bug,修归属)。环必须先判 a/b 再动作。

**跨节点**:②归属(给覆盖轴 theme×region)→ ④消费(算矩阵+发现盲区+判a/b)→ 回灌 L1采集 或 回灌 ②。

**触发条件**:②归属覆盖轴 + ④消费矩阵建成后才能闭环。

## B8 · ②-A 残留(71 入队 + 40 未 curate 域名)— 幂等可补

**是什么**:②-A apply 写了 128 篇,**71 篇保守入队未写**(`state/source_ready/2a_review_queue.jsonl`):
1. **60 篇 域名未收录**:政策的 gov 域名不在 `channel_registry`(40 个未 curate 的区县/不明域名,见 `channel_registry_needs_manual.jsonl`)。**~24 个可识别区县**(海珠/从化/深圳光明/重庆各区…)补进 `refdata.CITY_PINYIN` 或 channel_registry → 重跑 seeder+apply(**幂等,只补不重做**)即收掉。~16 个不明域名需查。
2. **9 篇 与 ledger 矛盾**:resolver 确定性结果 ≠ LLM ledger 的 suggested_issuer_short → 保守未写 → 人工/②-B issuer 规范化裁决。
3. **2 篇 date 破损落款抽不到**(P_2027/P_1900_SX,见 B4)。

**为什么不能忘**:这 71 篇 raw 身份仍破损(GO桶/未知region 等),没进归属轴会成孤岛。

**触发条件**:立即可做(curate 40 域名重跑)/ 或并入 ②-B。**捡起第一步**:读 `channel_registry_needs_manual.jsonl`,把可识别区县补 refdata → 重跑 `seed_channel_registry` + `run_2a apply`(幂等)。

**②-A 进展(2026-05-31,大头已收)**:加 `refdata.DOMAIN_OVERRIDE`(35 个区县/省级域名,用 sample_file 真机关名定省)→ 幂等重跑补修 **20 篇**(vault commit `2190d637`,累计 ②-A 修 148)。registry 164 域名,needs_manual 40→**5**。**残留入队 ~45**:5 个未识别域名的政策(pds/hnzy/lswz/tsgxq/wnd,多为国家级中继/信息不足)+ **9 与 ledger 矛盾**(待人工/②-B issuer 规范化)+ 2 date(B4)。这些是真长尾,可并入 ②-B 或专门小 pass。

## B9 · 月报原型退役 + 乡村去污染 + 派生 TAINTED — 重点治愈

**月报原型退役**:用户 2026-05-31 确认「策略-L3月报需求原型.md」是退役材料,已挖去归档 `00背景资料/_retired/`。它是 `report_blueprint.yaml` + `factcheck_rules.yaml` 的源 → 这两个已加 **TAINTED 头**,待 ④消费/L3 依新需求重生(`index.yaml` 已登记 `retired_tainted`)。

**乡村去污染**:乡村曾因一次月报讨论的误解(用户原意"充电业务适当关注乡村充电场景,有机会会做"→ 被 AI 误解成"专门做乡村业务")被抬成与三业务并列的**第4输出类目**,污染了 framework(report_blueprint biz_impact 4-key)+ 八步采集法 + **912/934 business_view**(影响分析.乡村,多为"无影响"=死重)。**已清(改源)**:`decision_framework.yaml` + `策略-八步采集法.md` 改回 **3-key**(加油/充电/电力),乡村并入充电机会型关注;**business_view 912 篇不手改,②-B 整文件重生时随 3-key prompt 自动清**(charter 改源重生非补丁)。

**残留引用(待处理)**:`00背景资料/策略-L2建设思路.md`(用户手写,引用月报原型 → **用户自查是否带同样过时假设**);历史日志(开发日记2026-04-27、pipeline review 2026-05-19)= 历史留痕不改。

**触发**:report_blueprint/factcheck 重生 = ④消费/L3;乡村清理验证 = ②-B 重生 business_view 时(验收门加一条:新 business_view 0 个乡村 key)。

## B10 · ③分析节点 = 政策关系/演进/区域(现存但 stale,待重生) — 推后到 ②-B 收尾后

**是什么**:政策↔政策的**跨篇关系层** = 四节点的 ③分析(②归属是单篇,③是跨篇)。涵盖用户关心的三类:**演进**(`supersedes` 显式废止 / `iterates` 升级v2)、**关联·国家级→省市跟进**(`derives_from` 国家级追溯·省市派生自国家级 / `cites_basis` / `references` / `aligns_with` 同主题跨部门对齐)、**区域**(`extends` 试点→全国·region 跳变 + 各篇 region 做区域热度/差异对比)。SCHEMA §5.2 已定义这 9 类。

**现状(2026-06-01 探明,实测)**:vault `1_extracted/relations/` **已有 8 个关系文件**(derives_from 326KB / references 173KB / cites_basis 258KB / aligns_with 94KB / clarifies / extends / iterates / supersedes)+ `_index_by_policy`(723 篇索引),抽取器在 `scripts/l2_derive/`。**但全是老 L2(4/28–5/12)产物,产于 raw 清洗(999→935)+ ②-A 改 id/region + ②-B 挂 theme 之前** → 引用旧 id/未归属语料,**stale 不可信,须整文件重生**(非补丁)。

**为什么必须 ② 先于 ③**:关系吃"归属"当输入——`derives_from`(国家级→省级跟进)要先知道两篇挂同一 theme + 各自 region 层级;`aligns_with`/`extends` 同理。老关系不可靠的根因正是抽于"没干净归属之前"(没编目就连书)。

**触发**:②-B(gold 冻结 + 935 跑完写 business_view)落地后。**不从零**:老 `l2_derive` 抽取器 + SCHEMA §5.2 当设计种子,在干净+已归属语料上重生这 9 类。设计待 ②-B 收尾再做,本条只钉 scope。

**关联**:B7(江浙等区域覆盖盲区)= ③关系+region 的一个 ④消费场景,同一条依赖链(②→③→④)。

---
_登记于 2026-05-30。新增推后项往下追加,不删旧项;做掉的标 ✅ done 并注日期。B2–B5 登记于 2026-05-31。B6–B7 登记于 2026-05-31(采集未补齐 + 2线可操作 + 盲区反馈环)。B8 登记于 2026-05-31(②-A 71 入队残留)。B9 登记于 2026-05-31(月报原型退役 + 乡村去污染)。B10 登记于 2026-06-01(③分析=关系/演进/区域,现存8文件但 stale 待重生,依赖②)。_
