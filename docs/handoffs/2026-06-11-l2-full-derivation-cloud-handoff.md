# Handoff:L2 全派生栈上云(新 session 接续)

> 自包含交接。新 session 读完此文 + memory `migration-s2-single-producer-nas-exit` 即可接续。
> 目标:把**整条 L2 派生流水线**(③关系 + 信号 + 实体/观点 + 分类/摘要 + 行业情报B1 + 结晶)从建设期"本地手工/oneshot 跑"操作化为"云上自动持续跑、数据完全由云上接管"。
> **用户红线态度(2026-06-11 原话)**:"这些东西之前架构的,都是本地做完之后交付给线上的完整产品,为什么你会恐慌到要切分?这个问题比面对的困难本身更严重。" ⇒ **不许把整栈碎成"只做归属",全栈都要上云。**

---

## 0. 一句话现状

S2 单生产者迁移:**三线(评论 + 政策 + L2 归属/business_view)已云上全自动**,2026-06-11 首个无人值守周期**全绿**。但 L2 派生只自动了"归属"一层,**③关系 + 其余 8 个派生模块全部冻结在建设期**(本地产物,未上云)。下一步=整栈上云。

---

## 1. 落盘快照(2026-06-11)

### Git(main,GitHub `ZaynShao/policy-analysis-pipeline`)
- HEAD = `21c493a`(+ vault 侧机器 commit,见下)
- 本轮关键 commit:`9831ee5` L2 放宽同模型+死信代码 / `9bb1db2` L1 扫描并发 / `a396d62` L2 全 deepseek / 更早 `d7eb716` PR#6 S2 主体。
- **环境陷阱**:工作仓=主 checkout `/Users/shaoziyuan/dev/政策分析-pipeline`(branch main);session 默认 cwd 在 `.claude/worktrees/...`,**别在里面干活**(本轮 subagent 两次掉进去提交错分支)。主 checkout 有别条线的未跟踪文件(`docs/2026-06-09-*`、`docs/runbooks/fetch-proxy-*`、`scripts/service/fetch_proxy_health.py`、`docs/superpowers/*2026-06-09*`)和未提交 OPERATIONS.md 改动——**绝不 add/commit/改**。git add 永远只点名自己的文件。

### 服务器(阿里云东京 8.216.59.173)
- SSH:`ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`(settings.local.json 有 allow 规则,只读 recon Claude 能跑;生产写/部署默认要用户/bypass)。
- repo `/root/policy-pipeline-src`(= main),vault `/root/policy-vault`(身份 policy-pipeline-vps,可写 remote),运行时 state `/root/policy-pipeline-state`(容器内 `/state`)。
- 镜像 `policy-pipeline:latest`:**只有 compose 的 `policy-pipeline` 服务有 `build: .`,`policy-producer` 只引用同镜像**。重建必须 `docker compose -f docker-compose.server.yml build policy-pipeline`(`build policy-producer` = `No services to build` 的 no-op,本轮踩过、队列被旧镜像二次抽空)。重建后验证闸:`docker run --rm policy-pipeline:latest sh -c "grep -c <新符号> <文件>"`。
- 容器:`policy-pipeline`(vault:ro,投影消费)/ `policy-producer`(vault rw,生产线);env_file `/etc/policy-pipeline/{pipeline,models,commentary,notify}.env`(0600,值盲,不进 git)。
- **models.env = deepseek**:`OPENAI_API_KEY`/`OPENAI_BASE_URL` 装 deepseek(openai 兼容)。L2 gen+judge 都用 `deepseek-v4-flash`(`--gen-provider openai --judge-provider openai`,不需要 ANTHROPIC_*)。**MiniMax 已弃订(商务决策)**。
- openclaw gateway 常驻(systemd user+linger,feishu),告警通道通(用户 open_id 在 notify.env)。

### cron 终态(7 active,CST)
- `30 7` 评论 ingest(`--since 2026-06-06 --feed-timeout 600` + flock)
- `0 9` L1 政策 incremental(并发扫描)→ push → L2 队列
- `30 9` L2 归属(`run_l2 --gen-model deepseek-v4-flash --gen-provider openai --judge-model deepseek-v4-flash --judge-provider openai`)→ push
- `0 10` 投影 run_sync
- `30 9` QR 哨兵 / `0 */6` token 检测 / `0 21` sync_tick(既有)
- 全部共持 flock `/var/lock/policy-pipeline-producer.lock`(`-w 7200`=2h 预算;L1 串行扫 165 渠道,并发版 dry-run 实测 6m24s)。

### 今早审计(2026-06-11,首个无人值守周期,全绿)
- 评论:feed 5/ingested 0/dup 5(无新)。L1:scanned 378/**ingested 1**/pushed 25。L2:**processed 1 ok 1 failed 0**(同模型 warn 出现=预期),pushed 1。投影:synced **792**/relation **992**/errors=[]。**死信 l2_failures.jsonl 不存在,队列 0,vault 干净 HEAD==origin/main**。relation 992 没动=③ 没跑(符合现状)。

---

## 2. 全 L2 派生栈盘点(Explore 测绘,2026-06-11)

**11 个模块,只有 2 个用 LLM;9 个是确定性脚本(regex/启发式/聚合),又快又便宜。卡点共同:绝大多数只写 `state/` preview,"apply 到 vault"是单独/手动一步("由人另控")。`orchestrate.py` 现仅接 ②归属 + 投影,其余 9 个 runner 一个都没接。**

| 层 | 模块 | 入口(真实 CLI 以脚本为准,Codex 复核) | 消费 | 产出(vault 路径) | LLM | 增量/全量 | apply 现状 |
|---|---|---|---|---|---|---|---|
| ① 归属 | `l2_attribution.run_2a` | `run_2a {dry-run\|apply} --vault V --state state/source_ready` | 0_raw/policies + channel_registry | 写 0_raw fm 归属字段 + state | 无 | 全量扫 | apply 后手动 commit |
| ② 主题评分 | `l2_themescore.run_2b` | `run_2b {dry-run\|apply\|apply-accepted} --vault V --state state/node2b --gen-model M --judge-model M [--pid-file]` | 0_raw/policies + themes_registry | `_meta/business_view/{pid}.yaml` | **是 逐篇** gen pass1/pass2 + judge | 支持 `--pid-file` 增量 | dry-run→人审→apply ✅**已自动(per-pid cron)** |
| ③-B 高精度关系 | `analysis_high_precision_relations.run preview` | `--vault V --state P` | 0_raw/policies(tracked) | state hpr candidates | **无**(regex 文号) | 全量 | preview only |
| ③-C 语义关系 | `analysis_semantic_relations.run preview` | `--vault V --state P --hpr <hpr.jsonl> --judge-model deepseek-v4-flash` | policies + ③-B 候选 | state accepted_semantic_relations | **是**(只判 ③-B 圈出的候选对,**非全 N²**,有界) | 全量 | preview only |
| ③-D 关系视图 | `analysis_relation_views.run preview` | `--vault V --sem <sem.jsonl> --hpr <hpr.jsonl> --out P` | policies + ③-C + ③-B | state `relations_canonical.jsonl` + `_index_by_policy/_rev_{pid}.md` | 无(合并投影去重) | 全量重生边集 | **apply 不在本模块=缺口** |
| ③-E 关系清点 | `analysis_relation_inventory.run preview` | `--vault V --state P` | policies + 1_extracted/relations 存量 | state inventory 审计 | 无 | 全量 | audit only |
| ④ 上下文 | `analysis_context.run preview` | `--relations <canonical.jsonl> --policy-context <…> --state P` | ③-D + signal_context | state analysis_context | 无 | 取决上游 | preview only |
| ⑤ 行业情报B1 | `market_intel_signals.run dry-run` | `--vault V --manifest <json> --state P` | 0_raw/policies + themes + **manifest(外部清单)** | state market_signals | 无(关键字) | 全量 manifest | dry-run;**需 manifest 输入(来源待定:评论 ingest 的 market_intel_staging?)** |
| ⑥ 评论信号 | `commentary_signals.run dry-run` | `--vault V --state P` | 0_raw/commentaries | state signals | 无 | 全量 | dry-run |
| ⑦ 派生信号 | `derived_signals.run {preview\|apply}` | preview: `--commentary-state P --market-state P --state P`;apply: `--vault V --preview-state P` | ⑤⑥ 的 state | **apply 写** `1_extracted/{commentary_signals,market_intel_signals}.jsonl` | 无 | 增量 | **preview→apply 现成** |
| ⑧ 信号上下文 | `signal_context.run preview` | `--vault V --state P [--blocked-signals P]` | 1_extracted/{commentary,market}_signals | state policy/theme/region_context | 无 | 全量 | preview only |

**依赖拓扑**:② → ③-B → ③-C → ③-D →(apply 关系)→ ③-E/④;⑤⑥ → ⑦(apply)→ ⑧ → ④;最后 `sync.run_sync` 投影。
**已冻结产物(建设期本地做的,vault 里现有但不再更新)**:`1_extracted/relations`(1138 边/992 投影,停 6/8)、`entities`、`opinions`、`policy_classification.jsonl`、`policy_summaries.jsonl`、`market_intel_signals.jsonl`、`2_crystallized`(仅 4 篇)。
**orchestrate.py 现状**:`make_attribution_runner()` 已有(subprocess 调 run_2b apply);`run_crystallize` 钩子=None;③/信号/上下文**无 runner**。要全栈=补上表里 ✗ 的 runner 工厂 + apply 步 + 编排顺序。
**注意**:Explore 给的部分 CLI/参数是推断,**Codex 实施时逐个对脚本 `--help`/源码复核**,不照抄。SCHEMA.md §4(business_view)、§5.1(summaries)、§5.2/5.3(relations)有产物契约;entities/opinions/signals/crystallize 在 SCHEMA 标"待扩展"。

---

## 3. 架构提案(待新 session 与用户敲定后实施)

**两节奏并存:**
- **per-pid 增量(已有,保留)**:新政策归属 business_view,cron 09:30。
- **新增·夜间全派生 pass**:把全量重算的层(③关系族 / 信号族 / 上下文 / 结晶)做成一个**完整重建编排器**,L1/L2 之后跑:③-B→③-C→③-D→apply关系 / ⑤⑥→⑦apply→⑧→④ / 结晶 → 投影,每层 preview→apply 经 produce_and_push 落 vault(白名单分层)。

**唯一成本未知 = ③-C 的 LLM 候选对数量**(被 ③-B 文号规则收窄,有界)。**实施第一步**:跑一次 ③-B preview 数候选对 → 钉死 ③-C 成本 → 定 ③ 节奏(夜间全量 or 更稀疏)。

**用户在第 7 节最后一轮已被问"确认两节奏方向",尚未明确答复**——新 session 先确认架构,再写 spec(走 superpowers brainstorming→writing-plans→Codex 实施)。

---

## 4. 今天的执行计划(用户定调:地基必到 + 全派生同时开建,不预设砍层)

1. **地基(今天必到)**:
   - **424 归属 backfill**:0_raw/policies 1224 篇 vs business_view 800 篇 ⇒ ~424 篇无归属(日常 cron 只处理新增,存量永远补不上)。把无 business_view 的 raw 全入队 → run_l2 drain。
   - **L2 失败告警**:cron 不对死信增长告警、run_l2 exit 0 ⇒ 失败静默。补 cron 死信增长→notify。
   - **Mac 退役确认 + OPERATIONS.md 改单生产者**(W4 cutover)。
2. **同时开建全派生编排器**:③-B 数候选对(钉成本)→ 按依赖顺序逐层补 runner+apply(确定性层先上)→ 串编排 → cron。能上多少上多少。

---

## 5. 挂账清单(全)
- **424 归属 backfill**(存量 raw 无 business_view)。
- **L2 失败告警**(死信增长→notify;run_l2 exit 0 现状)。
- **③ 关系上云**(架构:增量 apply vs 夜间全量重建;apply-to-vault 缺口)。
- **行业情报 B1**(market_intel staged→signals 落地;manifest 来源待定)。
- **实体/观点/分类/摘要/结晶** 上云(各子系统)。
- **447/缺口**:vault ~1224 raw vs 投影 synced 792(≈432 未投影,口径待查 run_sync)。
- **L1 `--since` 死参数**(IncrementalConfig/CLI 有但从不传给 scan/filter,policy 全靠去重增量,日期无下限)。
- **judge 单模型质量**(gen=judge=deepseek-v4-flash,judge 自评退化,用户接受为 stopgap)。
- **drain 死信无自动重排 sweep**(已落死信,但无 sweep 回队)。
- 市监 backfill 孤儿 15 条(更早建设期遗留,已在某 commit 清过一批)。

---

## 6. 红线 & 分工纪律(必读)
- **凭据**:绝不进 git/不打印/不入摘要(models/notify/commentary/pipeline.env、wewe 码、飞书 appSecret、deploy key)。微信 token Claude 不碰。值盲手法(服务器侧文件到文件、grep 重定向)。
- **vault**:raw 只增不删;写只经 `produce_and_push`(白名单守卫),绝不手工 git add/commit vault。
- **分工**:完整任务(代码、多步运维)= **Claude 出设计/handoff → Codex 执行 → Claude 审收**。handoff 全文直接贴聊天给用户转交 Codex(文件版同时存 git)。Claude 只做侦察/单点查证/审收/手册本身。代码改走 TDD,**diff 必须 Claude 审过再合**。
- **server 写 gating**:SSH 生产写/部署默认 harness 硬拦,要用户亲手或会话级 bypass;只读 recon Claude 能跑。新 session 默认无 bypass。
- **反污染**:禁读 `~/政策分析-legacy-archive/`;不引 legacy 路径;schema 看 SCHEMA.md 不反推老脚本;oneshot 进 `scripts/_oneshot/` 7 天归档。
- **别碰**:`/root/safety-platform`、`platform-*` 容器、tyo-prod(8.209.197.50 用户另一套 openclaw)、Mac 的 wewe-rss 容器(保持停)。
- **Codex 偏差教训(本轮真实踩过)**:① produce_and_push 是 host python module,**必须先 `cd /root/policy-pipeline-src`** 否则 `No module named scripts`;② 镜像重建认 `policy-pipeline` 服务非 `policy-producer`;③ 中文文件名 git 操作必须 `-c core.quotepath=false -z`(NUL);④ policy 的 pid = frontmatter `id:` 字段(非 pid:);⑤ `drain_queue` 失败项现已落死信(`9831ee5`)不再静默丢。

---

## 7. 近 ~10 来回对话原文(供新 session 还原推理链)

> 用户消息逐字;Claude 回复保留全部决策/数字/代码,仅压缩冗长排版。

**[U1] Codex 报告**:Step 3 L2 失败,AssertionError `judge 模型必须 ≠ generator 模型`,`{processed:32, ok:0, failed:32}`。根因:run_2b 硬断言 gen≠judge,撞"gen+judge 都 deepseek-v4-flash"。副作用:drain_queue 处理后无条件 mark_complete,32 失败项已出队(队列 0)。列三选项:①改断言允许同模型 ②换不同模型 ③恢复 32 重排。
**[C1]**:读 drain_queue 确认第 65 行 `mark_complete` 无条件(失败也出队);服务器查实 l2_queue=0、ledger=0(干净)、raw 安全在 vault `feefc9b`。读 run_2b/make_client 确认 `--gen-provider openai`→OPENAI_*(deepseek),全 deepseek 不需 ANTHROPIC_*,但同模型撞断言。建议:不放宽断言(judge 独立性是真保护),用两个不同 deepseek 模型;问用户第二个模型 + drain wart 修不修。

**[U2]**:"放宽，只保留1家，修"(放宽断言=单模型 deepseek;修 drain wart;MiniMax 不订阅永久)。
**[C2]**:读 run_2b 断言行(line 362)、orchestrate drain/save_ledger/StageResult、l2_queue API、corpus.load_policies(pid=`fm["id"]`)。验证 feefc9b 提 pid(踩中文名 quotepath:须 `-c core.quotepath=false -z`)。写 handoff `2026-06-10-codex-l2-relax-deadletter-recover.md`:Part1 两改(warn_if_same_model 替断言 + _record_failure 死信,TDD)、Part2 合并部署、Part3 恢复 32(host 取 feefc9b 清单→容器 enqueue_batch,25-35 安全闸)、Part4 重跑 L2→push→投影→Step5 解 cron。commit `8b0b74b`。

**[U3] Codex**:Part1 完成停审查点,分支 `fix/l2-relax-deadletter` HEAD `9831ee5`,TDD 红绿证据,全量 566 passed,diff stat。
**[C3]**:fetch 真分支审 run_2b+orchestrate 全 diff(断言→warn、死信两分支、save_ledger 只在 res.ok),审测试(死信测试断言出队/记录/不进账/ledger_path 不存在),本地复跑 28 passed,还原主 checkout。**审过,GO**:合 main→重建镜像→恢复 32→重跑 L2→push→投影→Step5。

**[U4] Codex**:按红线停。本地已 ff 合 main `9831ee5` 并 push,服务器 reset 到 9831ee5,但 **L2 又失败同 assert**。诊断:host 是新码但容器内 run_2b 仍旧码;`docker compose build policy-producer` 输出 `No services to build`(policy-producer 无 build 字段);队列又被旧镜像抽空(0),死信也没生成(旧镜像无该修复)。建议改 `docker build -t policy-pipeline:latest .`。
**[C4]**:读 compose 确认 `policy-pipeline` 服务才有 `build: .`。只读验证当前镜像:run_incremental 有 ThreadPoolExecutor(scan-concurrent 在)、run_2b 仍旧 assert、orchestrate 无 _record_failure(镜像停在 21:15 scan-concurrent 那次构建)。修 handoff Part2:build `policy-pipeline` + 加镜像验证闸(grep warn_if_same_model/_record_failure 都≥1 才往下)。commit `21c493a`。GO:重建正确服务→验证闸→再恢复 32→重跑。

**[U5]**:"有个问题，codex还在跑，我困了但是明天cron要真开始跑了"。
**[C5]**:明早一定跑的=成熟线(评论/投影/哨兵/token,安全);只有 L1(09:00)+L2(09:30)是新线、且只在 Codex 跑到 Step5 解注释才触发。建议今晚别让 L1/L2 自动上线(L2 无失败告警、睡着不会被叫醒)。方案:让 Codex 完成到投影、**停在 Step5 之前不解注释**,明早人工确认再解。给停 Codex 的话术。

**[U6]**:"codex不是只收到L2的任务吗?"
**[C6]**:纠正——那份 L2 手册 Part4 末尾就是接到 Step5 解 cron,且我上条 GO 也写了"→Step5 解注释",所以按现指令 Codex 跑完会自己解 cron。stop 消息不是多余、得发。

**[U7]**:"离做完也就差个step5吗？那我等一下算了"
**[C7]**:纠正——不止 Step5。真正没成功过的是 **L2 重跑本身**(两次都失败:assert/旧镜像)。剩余=重建镜像→验证闸→恢复 32→**重跑 L2(从没通过)**→push→投影→Step5。可能再失败再拉我。Step5 已被拦,无论成败都适合睡一觉再看,无"睡着了坏东西自动跑"。建议发 stop 直接睡。

**[U8] Codex**:"完成。Part2–4 已跑完,三线自动化已解禁"。镜像验证闸 warn_if_same_model:2 / _record_failure:3;恢复 `re-enqueued 32`;**L2 `{processed:32, ok:32, failed:0}`**,队列 0,无死信;派生 push 31 paths;投影 synced 791/relation 992/errors=[];**cron 09:00+09:30 已解注释**,L2 行已改 deepseek,active 7;vault 干净 HEAD==origin。偏差:首次 L2 push 漏 cd(无写入)随后重跑成功。+ 问:"现在是L1L2的评论+政策+行业情报+派生都已经完成了吗?"
**[C8]**:拉齐——评论✅ 政策✅ L2派生✅(**仅今晚新增 32**)。**两个没完成**:① **行业情报=market_intel 只暂存不落地**(评论 ingest stage_market_intel 写 state json 不入 vault,等 B1,B1 没建/没进 cron);② **L2 全量没到最新**:vault ~1238 raw vs synced 791 ≈ 447 缺口(建设期遗留,VPS L2 ledger 此前全空)。watch-item:L2 cron 无失败告警→明早主动看 l2.log/l2_failures。更新 memory。

**[U9]**:"为什么L2的派生怎么少，L2的3不是'两两'关系吗?"
**[C9]**:核 orchestrate——③ 关系是 Phase 1 **no-op 钩子**(docstring 明写"pairwise 全量、③-C 未 apply、不硬造增量");run_l2 调 drain 只传 run_attribution(没 run_crystallize)。证据:relation_count 992 没动。③ 关系是单独全量重建(rel992=6/7 手动),不在任何 cron。L2 多层派生今晚只自动了归属一层(关系❌停6/7、结晶 run_crystallize=None)。这是"③增量 apply 路径"缺口。

**[U10]**:"观察一下早上跑的结果，然后规划一下：L1+L2机制全量上云(尤其是③还没碰的问题)，且产出数据完全由云上接管，还差了哪些，今天做完"。
**[C10]**:晨审全绿(见 §1.今早审计)。侦察派生栈:1224 raw vs 800 business_view(424 无归属);1_extracted 有 relations/entities/opinions/classification/summaries/market_intel_signals;2_crystallized 仅 4;scripts 下 analysis_* / l2_* / *_signals 近 10 模块。读 ③ relation_views docstring(多模块、apply 由人另控)。**初判太大→提议切分(地基先做、③留设计)+ AskUserQuestion 问今天范围 + 哪些层 canonical**。

**[U11]**:答 Q1="选归属层全量化+可靠+退役没问题，但不是明确的不上线，根据今天工作量定";答 Q2(关键纠正)="这些东西之前架构的,都是本地做完之后交付给线上的完整产品,**为什么你会恐慌到要切分?这个问题比面对的困难本身更严重**"。
**[C11]**:**接住纠正,收回"切分"的怯**。目标改为整栈操作化上云。派 Explore 测绘全派生流水线(§2 即其成果)。回来后提架构(两节奏:增量归属 + 夜间全派生 pass)、点出唯一成本未知=③-C 候选对(有界)、今天=地基必到+全派生同时开建不砍层。**问用户确认架构方向**(待答)。

**[U12]**:"你把目前落盘的进度、现状、盘点出来的已知模块、近10个来回的对话原文合并做一个handoff，我在新的session开始做"。
**[C12]**:本文件。

---

## 8. 新 session 第一步
1. 读本文 + memory `migration-s2-single-producer-nas-exit`(状态真相源)。
2. 与用户敲定 §3 架构(两节奏)。
3. 走 superpowers brainstorming→writing-plans 出 spec/plan,Codex 实施,Claude 审。第一技术动作=③-B preview 数候选对钉死 ③-C 成本。
4. 地基(424 backfill + L2 告警 + Mac cutover)可并行先落。
