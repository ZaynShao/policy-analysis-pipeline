# 政策分析 Pipeline · 工程仓 CLAUDE.md

## 这是什么仓

这个仓库是**政策分析项目的"工程层"**——脚本、SOP、状态、文档全在这里。
**数据**(政策 raw、派生产物、business_view)住在另一个仓:vault。

两仓通过 SCHEMA.md(数据契约)解耦。pipeline 通过 schema 读写 vault,vault 不感知 pipeline 实现。

```
~/Documents/Zayn Main/政策分析/   ← vault(数据 + 数据契约 SCHEMA.md)
~/dev/政策分析-pipeline/           ← 本仓(工程)
~/政策分析-legacy-archive/         ← 已废弃的旧脚本/产物(物理隔离,本仓不读)
```

---

## 反污染纪律(本仓建立的初衷之一)

历史项目积累了大量"屎山":27 个 oneshot 脚本、11 个 staging 目录、30+ 散文件、过期文档。
本仓是 clean slate,守住下面纪律才不会再长成屎山:

### 1. 不读旧 repo

`~/政策分析-legacy-archive/` 目录**禁止读取**。需要历史信息只查 LESSONS.md。
任何"参考一下老脚本怎么写的"的冲动都是错的——老脚本里的设计正是本次想推翻的。

### 2. 不引旧路径

任何文档、脚本注释、commit message **不允许出现** legacy archive 路径或老 repo 内部路径。
讨论历史用"建设期"、"上一代实现"等抽象表述。

### 3. Schema 是契约,不是从代码反推

vault 字段定义只看 SCHEMA.md。
**不允许**通过 grep 老脚本来"理解 schema 是什么样"。
需要看现状时,直接看 vault 内的实际数据样本(读 1 份 raw policy 即可),而不是读老抽取脚本的逻辑。

### 4. Oneshot 只能进 scripts/_oneshot/

- 一次性脚本(数据迁移、批量修复)进 `scripts/_oneshot/`
- 跑完立即在 commit message 里标 `[oneshot complete]`
- 7 天内未归档的 oneshot 视为"伪 oneshot",合并 PR 时拦截
- 如果某个 oneshot 跑了 ≥2 次,说明它不是 oneshot,要么提到正式管道,要么修复 root cause

### 5. LESSONS 是原则不是索引

`LESSONS.md` 只写"规则 + 理由 + 触发场景 + 处置",**不引具体文件名/路径/commit hash**。
违反这条会让新阶段的 AI 又被拉回参考具体老代码。

---

## 仓内目录结构

```
.
├── README.md            项目对外说明
├── SCHEMA.md            数据契约(vault 字段定义,与 vault 同步)
├── OPERATIONS.md        当前生效的运营手册(SOP 合并版,带 changelog)
├── LESSONS.md           踩坑沉淀(原则化,不引具体路径)
├── CHANGELOG.md         本仓变更日志
├── CLAUDE.md            本文件
│
├── scripts/
│   ├── l1_collect/      L1 采集(抓取 / 入库 / 评论关联)
│   ├── l2_derive/       L2 派生(实体 / 关系 / business_view / 主题结晶)
│   ├── l3_render/       L3 渲染(月报 / 决策卡片)
│   ├── audit/           lint / 校验 / status 生成
│   └── _oneshot/        一次性脚本(7 天内归档)
│
├── state/               运行时状态(staging / audit 输出 / last_run)
│   └── .gitignore       state 内大部分内容不进 git(各子目录单独配置)
│
└── docs/                深度文档(策略推导 / 历史决策 / 设计思考)
```

---

## Vault 路径与读写约定

**vault 根**:`~/Documents/Zayn Main/政策分析/`

**Pipeline 读 vault**:
- `0_raw/policies/*.md`        — 政策 raw(只读,**永不修改**)
- `0_raw/commentaries/*.md`    — 评论 raw(frontmatter 关系字段允许通过专用脚本修改,见 SCHEMA §C)
- `_meta/business_view/*.yaml` — 业务派生(可读可重写,**整体重写不就地编辑**)
- `1_extracted/`               — 通用派生(可读可重写)
- `2_crystallized/`            — 结晶页(可读可重写)

**Pipeline 写 vault**:
- 通过 SCHEMA 校验脚本入库
- 写之前必须 dry-run 看变更集
- 任何写入都记 `state/last_run.json`

**Pipeline 不写 vault**:
- 不在 vault 内创建工作中间产物(staging / audit 输出 / tmp)
- 中间产物全部进 `state/`

---

## 关键运行入口

```bash
# 状态自检(查 vault 与 SCHEMA 是否一致 + 当前数字)
python3 scripts/audit/dump_status.py

# L2 派生增量跑(读 vault raw,写 vault 派生)
python3 scripts/l2_derive/run_pipeline.py --vault ~/Documents/Zayn\ Main/政策分析

# 完整 L3 月报渲染
python3 scripts/l3_render/render_monthly.py --month 2026-05
```

(脚本骨架陆续补,详见 OPERATIONS.md)

---

## 评论 RSS 入库(L1 commentary)

评论采集 = wewe-rss(微信公众号→JSON feed)→ `scripts/l1_collect/commentary_ingest/`。

**部署纪律(重要)**:token 是个人微信读书账号,**必须从国内 IP 发起**——东京服务器机房 IP 会触发微信地理风控(最坏冻结账号)。故此线跑**国内节点**(阶段一 Mac,阶段二国内容器),写 Mac vault 经现有 rsync 上服务器只读消费,**不在东京服务器跑 discovery、不写 /root/policy-vault**。

- 运行:`python3 -m scripts.l1_collect.commentary_ingest.run --feed-url ... --vault-dir ... --db-path ...`(路径/凭据全 env/CLI,零硬编码)
- 迁移:`docs/runbooks/commentary-rss-ingest-migration.md`(方法更新时同步维护本节与该 runbook)
- 保守轮询:轮询越勤→token 废越快→扫码越频繁。CRON 维持 6h/次量级。
- feed limit 别被限住:wewe-rss 不带 `limit` 默认仅 30 条/次,15 号合并会静默漏。`WEWE_FEED_URL` 必须显式给大 limit(如 400);代码不硬编码 limit,`coverage_warning` 是兜底信号。

---

## 与 vault CLAUDE.md 的分工

- **vault CLAUDE.md** — 给在 vault 里写作/浏览的 AI 看,说"这是只读数据仓,工程见 pipeline"
- **本 CLAUDE.md** — 给在 pipeline 里实施的 AI 看,说"这是工程仓,反污染纪律是这五条"

两份各管各的 cwd,不交叉引用。
