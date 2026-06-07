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

**进展(2026-06-03)**:
- `market_intel` 最小 representation dry-run 已完成:从 `state/source_ready/market_intel_manifest.jsonl` 读取 23 条,通过当前 raw `id` 或 `aliases` 全部定位到 `0_raw/policies`,输出 23 条内部市场验证 signal。
- 工程证据:`state/market_intel_signals/dryrun_20260603/market_signals.jsonl`、`review_queue.jsonl`、`summary.json`、`reports/market_intel_signals_dryrun.html`。
- 人工池 14 条:11 条 `theme_not_found`(多为风电/光伏/补贴/价格等不在当前 13 主题内或弱主题),3 条 `region_unknown`。这说明第三源表示已可复现,但是否扩主题/业务线还需后续分类法判断。
- 本 dry-run 不写资料库、不移动 raw、不调用模型;市场信号仍作为内部验证参数,不作为消费层外显方法论。

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

**强化项(2026-06-01,gold 评审反馈)**:用户要求**不可能年份自动套停**——加一条 ②-A 确定性**年份合理性通则**(年份 ∉ [合理下限~1949, 今年+1] → 自动拦截/入队,如 1900/2027/2048)。**机制级修(非补丁)**:规则长在 ②-A resolver、对全量一视同仁;具体篇的日期走 ②-A 既有纠正路径(确定性重算 / §D 重抓 / 人工队列 + §C provenance),**绝不 pid 硬编码日期**。与本条 date 修正一并做。

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

**gold评审反馈(2026-06-01)·过期政策彻底检测**:②-B 已就"文本自标失效/废止"做了提示词规则(D2 按无现行约束力打低,theme 照挂)。但**"被哪篇废止/取代"的彻底判定**要靠 ③ 的 `supersedes` 关系——建 ③ 时,`supersedes` 抽取器(通则,全量重生)+ 下游"被废止→按过期处理(D2低/不当 actionable)"一并设计。**机制级**:跟着关系层整体重生,非逐篇补。

**③-A 进展(2026-06-04)**:关系资产审计 preview 已完成,只读旧 `1_extracted/relations/*.jsonl` 与当前 git tracked raw 政策。实测 tracked raw 935 篇,未跟踪 raw 1 篇已排除并单独计数;旧关系行 2000 行,其中 archive 行 89,缺失/空端点行 524。工程证据:`state/analysis_layer/preview_20260604/relation_inventory.json`、`relation_rows.jsonl`、`reports/relation_inventory_preview.html`。本 preview 不写资料库、不写 raw、不 apply、不调用模型;旧 relation 行只作为审计输入,不能作为新 ③ accepted 输出。

**③/④ 模型约束(2026-06-04 补充)**:后续凡接模型的 ③/④ 子流程,必须按普通模型可接入设计(MiniMax/DeepSeek 等),保留并强化既有硬化 prompt、schema 校验、program gate、审计门和人工池阻断。正确性不能依赖强模型自由发挥;不确定样本必须进人工池并等人工结论回流正常 dry-run/apply,不能被标记后继续下塞。

**③-B 进展(2026-06-04)**:高精度政策关系 preview 已完成第一版确定性抽取,只读当前 git tracked raw 政策正文与 frontmatter 文号,不读取旧 relations 作为 accepted 输入。实测 tracked raw 935 篇,未跟踪 raw 1 篇已排除,可索引文号目标 399 个;产出候选 677 条:`references` 424、`cites_basis` 161、`supersedes` 5、`clarifies` 87。工程证据:`state/analysis_layer/preview_20260604/high_precision_relation_summary.json`、`high_precision_relation_candidates.jsonl`、`policy_relation_candidates/*.jsonl`、`reports/high_precision_relation_preview.html`。本 preview 不写资料库、不写 raw、不 apply、不调用模型;`supersedes` 已按高精度原则收紧为目标文号后近距离出现明确废止/停止执行/失效,不再把泛化"替代/取代"当废止。

**③-E v1 进展(2026-06-04)**:`analysis_context` preview 已完成第一版合成,把③-B高精度关系候选与③-D已闭环 `policy_context` 合并为 policy-level 上下文。实测输入关系候选 677 条、policy context 87 条;产出 analysis context 342 条,其中 293 条有关系上下文、87 条有信号上下文、38 条两者都有。主要 flags:`has_references` 293、`has_basis_chain` 177、`has_clarification` 87、`relation_only_no_signal_context` 255、`signal_only_no_relation_context` 49、`no_market_validation` 77、`market_validation_weak` 10、`superseded_by_policy` 5。工程证据:`state/analysis_layer/preview_20260604/analysis_context.jsonl`、`analysis_context_summary.json`、`reports/analysis_context_preview.html`。本 preview 只写工程仓 state,不写资料库、不写 raw、不 apply、不调用模型,不消费 review queue 或 blocked signals;它不是最终业务洞察,也不代表③关系层完成。④可以先做读取契约说明,但实质消费层应等待③-C语义关系 preview 和③-E v2。

**③-C 机制设计(2026-06-04)**:已补充语义政策关系生成机制,明确 `derives_from`、`extends`、`aligns_with`、`iterates` 不能靠当前③-B确定性程序直接完成,必须等②-B覆盖足够或用户批准明确子集后,按“程序候选 → 普通模型受限判定 → schema/program gate → 人工池阻断 → preview/apply”执行。`conflicts_with` 默认不自动 accepted,只作为审计提示或人工池。工程证据:`docs/superpowers/specs/2026-06-04-analysis-semantic-relations-design.md`、`docs/reviews/2026-06-04-analysis-semantic-relations-brief.html`。

**②-B 为③-C补覆盖 dry-run(2026-06-04)**:已按全局选样规则跑一批 ③-C seed 扩展样本,只读 tracked raw、当前 business_view 和③-B关系 preview,优先选择当前 business_view 的关系邻居及高价值主题附近政策。模型通道:MiniMax-M2.7 生成 + DeepSeek reasoner judge;为适配 reasoning judge,已把 judge token headroom 从 1024 提到 2048。实测选样 24 篇,accepted draft 19 篇,入队 5 篇,分布告警 0。工程证据:`state/node2b/dryrun_v12_3c_seed_expansion_rerun/summary.json`、`proposed_changes/drafts_full.jsonl`、`review_queue/queue.jsonl`、`reports/coverage_expansion_summary_zh.html`、`reports/apply_preview.html`。本 run 不写资料库、不写 raw、不 apply;入队项不得进入③-C或④下游。

## B11 · ②-B 人工确认池与全局硬化回流 — 新增

**是什么**:②-B dry-run/apply 后留下的 `review_queue/queue.jsonl` 是**人工确认池**,不是待手工 apply 清单。当前 50 篇样本中 accepted 39 已按离线 scoped verify 写入,剩余 11 入队,暴露的是机制边界,不能逐条补丁处置。

**为什么必须单独登记**:这类队列是保守机制的正常产物。如果继续逐篇人工判断"该不该收",容易滑坡成 PID 白名单;如果强行跑到清零,又会浪费模型并把不确定性伪装成自动化结果。

**当前暴露的全局问题**:
1. judge evidence window 只看正文前段,会把正文后半的 V2G/VPP/桩车比等证据误判为不存在。
2. theme id 需要 canonicalization,如模型输出 `v2g_theme` 应归一到 registry 中的 `v2g`。
3. prompt 已允许零主题,但 `program_gate` 仍把 `themes=[]` 一律拒绝,规则不一致。
4. pass2 JSON 结构需要更强的全局约束或失败重试,避免把 `行动建议` 嵌进 `影响分析`。
5. 标准制定、目录、名单、弱提及不等于直接业务影响,需要作为全局边界进入 prompt / judge / 回归样本。

**处置原则**:
- 先把队列样本当"回归验证样本":它们只用来检查全局规则有没有修好,不是逐条人工处置表。
- 全局修复后只用这 11 篇重跑一次小范围 dry-run:不写 vault、不自动接收 queue、只看同类错误是否收敛。仍残留的才进入人工确认池。
- 人工确认池闭环:全局规则无法判断 → 入队 → 人工读证据 → 给出"放在哪/放入哪些/保持待办"裁决 → 记录理由/provenance → 回正常流水线 dry-run/apply。人工裁决可以是单篇数据结论,但不能变成源码 PID 特例或绕过流水线的手工写入。
- 多条人工裁决若暴露同一模式,再沉淀为分类法/registry/规则调整。

**触发条件**:②-B 下一轮全量 dry-run 前。**捡起第一步**:先做 `judge` 证据窗口 + `program_gate` 零主题一致性 + theme id 归一化的 TDD 硬化,再用 11 条队列样本小范围 dry-run 验证。

## B12 · 三源接线与旧 business_view 消费隔离 — 新增

**是什么**:2026-06-03 三源接线现状审计确认:政策源已进入 ②-A/②-B 主线,评论源和 market_intel 已被 schema/backlog 承认,但还没有形成同等可复现的归属、分析、消费路径。旧 `business_view` 仍大量留在可消费资料库中,且多数保留过时的"乡村"影响口径,会污染后续 ③/④。

**为什么必须单独登记**:这不是某几篇政策的分类问题,而是四层重构的系统边界问题。如果继续直接全量推进 ②-B,会把 policy-only 的归属结果误当成政策情报系统完成态。该问题不能用 PID 白名单或逐篇人工处置解决。

**当前证据**:
- `0_raw/policies`:935 篇。
- `0_raw/commentaries`:283 篇,其中 189 篇已有 `related_policy` 线索。
- `_meta/business_view`:955 个文件,新 ②-B 流程标记仅 11 个;862 个仍含 `影响分析.乡村`;863 个影响分析 key 不符合当前三业务口径。
- `state/source_ready/market_intel_manifest.jsonl`:23 条,仍是轻量承认,不是第三源 representation。
- 报告:`docs/reviews/2026-06-03-policy-intelligence-source-wiring-audit.html`。

**进展(2026-06-03)**:
- 旧 `business_view` 消费隔离已完成:dry-run manifest 955 行 → apply 隔离 905 个旧产物,保留 50 个当前 ②-B 脚本产物。
- 资料库内 `_meta/business_view` 当前剩余 50 个,均为 `scripts/l2_themescore/run_2b.py` 产物;其中 `MiniMax-M2.7` 39 个、`MiniMax-M2.7+judge-crosscheck+manual-review+v11-global-hardening` 11 个。
- 库外 backup:`/Users/shaoziyuan/dev/policy-analysis-backups/business_view_isolation_20260603_apply`。
- 工程侧审计证据:`state/business_view_isolation/dryrun_20260603/manifest.jsonl`、`apply_log.jsonl`、`reports/business_view_isolation_apply.html`。
- `commentary_signals` 最小 dry-run 已完成:只读 283 篇 `0_raw/commentaries`,对 189 篇已有 `related_policy` 的评论产出内部校准 signal;52 篇 `not_policy_related` 跳过;42 篇无关联跳过;18 篇进入人工池(15 篇主题未命中,3 篇正文不可读)。报告和机器证据在 `state/commentary_signals/dryrun_20260603/`。
- `market_intel_signals` 最小 dry-run 已完成:23 条 manifest 全部定位 raw,产出 23 条内部验证 signal;14 条进入人工池(11 条主题未命中,3 条地区未知)。报告和机器证据在 `state/market_intel_signals/dryrun_20260603/`。
- `derived_signals` preview/apply 契约已落地并执行 live apply:`review_queue` 已从"只统计"纠偏为发布闸门。当前 preview 候选 189 条评论信号 / 23 条市场信号,实际发布 171 条评论信号 / 10 条市场信号,拦截 31 条待人工闭环信号(18 条评论、13 条市场)。apply 只允许从 preview 输出整体写入 `1_extracted/commentary_signals.jsonl` 和 `1_extracted/market_intel_signals.jsonl`,不写 raw。
- `signal_context` preview 已完成:只读已发布的 171 条评论信号和 10 条市场信号,blocked 31 条只作为审计门,产出 87 个 policy context、13 个 theme context、10 个 region context。工程证据:`state/signal_context/preview_20260604/policy_context.jsonl`、`theme_context.jsonl`、`region_context.jsonl`、`summary.json`、`reports/signal_context_preview.html`。本 preview 不写资料库、不写 raw、不 apply、不调用模型,且不把 blocked signals 当 accepted。
- `signal_context` 暴露 2 条 market region 质量 warning:`province_code_with_city_name`(省级 code 搭配城市名),涉及 accepted market signals 的上游 region 规范化,后续应回流到 market_intel 表示/人工池规则,不能在 context 层逐条改。
- 本条剩余部分:人工池裁决如何回流到分类法,market_intel region 规范化如何收敛,以及 ④如何消费 `signal_context` 而不外显原始评论/市场证据。

**处置原则**:
- 旧 `business_view` 不应继续作为可消费资料库的可信输入;最大妥协是库外 backup,不参与 pipeline。
- 评论作为内部校准层,不直接改写 policy raw、policy themes 或 `business_view.scores`。
- market_intel 作为执行/机会验证信号,不混入 policy 或 commentary。
- 消费层外显结论、影响、建议和必要政策依据;评论与市场信号默认作为内部校准/验证参数,仅在追溯或审计时展开。

**触发条件**:继续 ②-B 全量重生、启动 ③分析重生、或启动 ④消费层之前。**下一步**:做小范围 `commentary_signals` 闭环,再处理 market_intel representation。

---

## B13 — CONTRACT-REL-1:③ canonical 关系格式 ↔ 服务化 sync relation_mapper 对账 ✅ done 2026-06-07

**✅ 已解(2026-06-07,commit `a6aba37`)**:③ 关系层已 apply 进 vault(HEAD `a6fb3c09`),关系=单文件 `1_extracted/relations/relations_canonical.jsonl`(字段 `from`/`to`/`rel`/`confidence`/`evidence`,1138 条,rel 词表 8 类全 ∈ VALID_RELATION_TYPES,仅缺 conflicts_with;`from`/`to` 全 P_ pid;evidence str)。修法=`collect_relation_rows` 读取边界把 `from`/`to`/`rel` 归一为 `from_pid`/`to_pid`/`relation_type`,`map_relation` 一字未动(3 测试覆盖 canonical/未知 rel/残缺行)。本地彩排实证:relation **998 行**落库(canonical 1138 中两端都在已同步 767 政策内的;140 条某端不在被丢=正确)。↓ 原始延后记录:

**发现**:2026-06-06,pipeline origin/main 阶段性 push 了 ③ 关系层投影器(`scripts/analysis_relation_views/`,commits a5266ec/bd61206/8b6d945/ab2d542)。它产 `relations_canonical.jsonl`,边字段为 **`from` / `to` / `rel`**(见 `api_view.py` 的 `to_row()` 输出 + 排序键)。而服务化线(分支 `feat/service-deploy`)的 `scripts/sync/relation_mapper.py` + `run_sync.collect_relation_rows` 吃的是 **`from_pid` / `to_pid` / `relation_type`**,并以这三键做存在性过滤。

**后果(若不对账)**:③ 关系真 apply 进 vault 后,sync 对每条 canonical 边过滤命中失败 → **静默跳过 → `PolicySemanticRelation` 表 0 行**。另:`pg_writer.build_relation_upsert` 写 `confidence`/`evidence`,需确认 canonical `to_row()` 是否携带,否则落空。

**为何延后(非现在修)**:① 关系 sync 本就按 spec §6 延后(首次 sync 只写 ②-B 政策,relations 表暂空);② ③ canonical 现为 preview(`run.py` 注记 `no_vault_write`/`no_apply`,落点 out_root 非 vault `1_extracted/relations/`),格式/落点仍可能动。现在改 = 追移动靶。

**强制对账点(触发条件)**:③ 关系 apply 进 vault 那一刻。届时二选一:(a) relation_mapper 改吃 `from`/`to`/`rel` 且 collect_relation_rows 读 `relations_canonical.jsonl`;(b) 加一层适配器把 canonical 归一化成 sync 入参。同时对齐:canonical 落点 vs sync glob 路径、confidence/evidence 字段、9 类 rel 取值集(SCHEMA §5.2)。**关联 B10**(③分析重生)。

## B14 — 人工处理/反馈机制交互设计(盘点先行·等 L1 机制落盘再启动) — 新增

**问题**:系统累积了 ~9 个"人在环里"触点、分 3-4 类不同性质,无统一交互设计。缺陷被机制检测后"丢进"池(IN 大体有),但"人处理完结论怎么出来"(OUT = 人交互面 + 回灌 pipeline 管道)没设计,有变僵尸池风险。

**盘点(起点·待扩充)**:缺陷/质量池(拒→人修)= ②-B review_queue / ②-A needs_manual / `sync_skipped.jsonl`(服务同步层·新) / B4 日期缺陷;覆盖/漏采反馈 = L1FeedbackQueue / B7;用户发起流 = ManualEntryRequest;校准/审计 = ②-B golden 抽查 / low-conf 队列。

**设计轴线**:① 每池处理人是谁 → 交互形态(平台运营 OPERATOR/HQ_GA/FIELD_GA → 前端 UI;builder/技术如 golden/low-conf → CLI/session/文件,别硬上前端);② 每池设计两半 = 人交互面 + 结论回灌管道(光界面无回灌=没闭环);③ Plan B 已规划前端审核页(L1FeedbackPool / ManualEntryModal 轮询 / PolicyDrawer override)= 已在途、别重做。

**硬约束(防膨胀)**:目标【不是】"统一审核中台"(各池生命周期不同·强行统一是错);要的是交互图 + 每池消费/回灌协议;先盘点出 HTML 文档再谈建。

**分阶段**:阶段0(现在)= 理解 + 进一步盘点(全仓 pipeline/vault/safety-platform/BACKLOG 找全)出 HTML;阶段1(等 L1 采集修复机制 Task11/12 落盘后)= 基于真实残留评估 + 设计交互面+回灌管道 + 建。**非阻塞·上生产前定下来**(否则池带上线无人消费)。可独立 session 做。

---
_登记于 2026-05-30。新增推后项往下追加,不删旧项;做掉的标 ✅ done 并注日期。B2–B5 登记于 2026-05-31。B6–B7 登记于 2026-05-31(采集未补齐 + 2线可操作 + 盲区反馈环)。B8 登记于 2026-05-31(②-A 71 入队残留)。B9 登记于 2026-05-31(月报原型退役 + 乡村去污染)。B10 登记于 2026-06-01(③分析=关系/演进/区域,现存8文件但 stale 待重生,依赖②)。B11 登记于 2026-06-02(②-B 人工确认池 + 全局硬化回流)。B12 登记于 2026-06-03(三源接线 + 旧 business_view 消费隔离)。B13 登记于 2026-06-06(CONTRACT-REL-1:③ canonical 关系格式 vs 服务化 sync relation_mapper 对账,延后到 ③关系 apply 进 vault;服务化部署线 feat/service-deploy)→ ✅ done 2026-06-07。B14 登记于 2026-06-07(人工处理/反馈机制交互设计·盘点先行·等 L1 机制落盘·独立 session)。_
