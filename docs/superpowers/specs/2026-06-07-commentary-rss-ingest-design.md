# Commentary RSS 自动入库闭环 · 设计 spec

**日期**:2026-06-07
**分支**:`claude/zen-saha-c3ac3c`
**所属**:L1 采集层(关联 backlog B3 commentary / B6 L1 采集未补齐)
**范围**:**token 有效状态下的自动抓取入库闭环**。扫码自动化(openclaw+IM)是后续独立 spec,不在本次。

---

## 1. 问题

政策评论(commentary)目前靠 wewe-rss 从微信公众号抓取,存在两个独立 gap:

- **G1 上游断流**:wewe-rss 不在跑 + 微信读书 token 过期(`accounts.status=0`,4-29 起断流 39 天)
- **G2 入库管道缺失**:wewe-rss → vault 从来不是自动流水线,一直是手工 oneshot

L1 正在服务化(部署到服务器变正式服务),本 spec 把 commentary 这条线做成**可在服务器自动跑**的闭环。消灭"手工批量入库",并把"token 失效"从"不知道断了还在等"变成"精确告警 + 已知操作点"。

---

## 2. 现状(已验证硬事实)

| 项 | 事实 |
|---|---|
| 工具 | wewe-rss(Node.js + SQLite),当前本机 `~/wewe-rss-data/wewe-rss.db`,非 Docker |
| DB 表 | `_prisma_migrations / accounts / feeds / articles` 四张 |
| articles 内容 | **无正文、无 url**,只有 `id / mp_id / title / pic_url / publish_time` |
| id 格式 | 全部 22 位纯 hash,`id → https://mp.weixin.qq.com/s/{id}` 映射 **100% 可靠**(2479 篇零例外) |
| token | 用户**个人微信读书账号**(邵子渊)的 JWT,存 `accounts.token`,当前 `status=0` 失效 |
| 订阅 | 15 个 feed,全 `status=1` 活跃 |
| 积压 | DB 2479 篇 vs vault 283 篇评论 |
| 历史入库 | 手工 oneshot(本仓之外),无自动管道 |

**根因**:token 失效(G1)+ 入库管道从未自动化(G2)。消灭手工维护,G2 必建,G1 靠"保守轮询 + 失效告警"管理。

---

## 3. 架构(选定 β:消费 HTTP feed)

wewe-rss **唯一不可替代**的功能:用微信 token **发现/列出**新文章 id(discovery)。此后 `id → URL → 正文` 我们自己全能做。因此接口选择是「用什么拿 discovery 结果」。

**选定 β = 消费 wewe-rss 的 HTTP feed(RSS/JSON)**,而非 α(直读 SQLite)。理由:
- 标准接口,跨 wewe-rss 版本稳定(不绑内部 Prisma 表结构)
- wewe-rss 全文模式由它扛微信反爬;feed 缺正文时我们 trafilatura 兜底
- 干净的 HTTP 服务边界,无共享文件系统/DB 写锁耦合
- 未来换 RSS 后端只换 adapter

```
微信公众号(curated 订阅)
   │  wewe-rss 用 token 发现新文章(discovery)— 唯一需 token 步
   ▼
wewe-rss 服务(Docker)──HTTP feed(优先全文模式)──┐
   │                                              │
   │  ingest 服务:                                │
   │   1. 拉 feed → 文章列表(title/url/date/[body])│
   │   2. 去重(vs vault + processed ledger)        │
   │   3. 结构性过滤(统一规则,见 §5)             │
   │   4. 正文:feed 有则用;无则 trafilatura 兜底  │
   │   5. 写 vault commentaries(仅追加)            │
   │   6. 记 ledger + last_run                      │
   ▼
vault 0_raw/commentaries/  +  state/commentary_ingest/
```

---

## 4. 组件

| 组件 | 位置 | 职责 |
|---|---|---|
| 入库脚本 | `scripts/l1_collect/commentary_rss_ingest.py` | 主逻辑:拉 feed→过滤→兜底抓正文→写 vault→记 ledger |
| feed adapter | 同上(内部模块或同文件函数) | 把 wewe-rss feed 解析成统一文章记录;隔离 wewe-rss 特定格式 |
| token 健康检查 | `scripts/l1_collect/commentary_rss_ingest.py --check-token` | 检测 token 失效(feed 全空/报错 或 DB accounts.status=0)→ 告警 |
| Docker 配置 | `docker/wewe-rss/compose.yml` | wewe-rss 服务定义(数据卷 + 保守轮询间隔) |
| 状态目录 | `state/commentary_ingest/` | `last_run.json` + `processed_ids.jsonl` + `market_intel_staging/` |

凭据(token / DB 路径 / vault 路径 / feed URL)全部通过 **env var / CLI arg** 传入,**绝不进 git**。

---

## 5. 过滤分层(L1 只做结构性,相关性留 L2)

按"采(L1)→加工(L2)"分层:"是不是能源政策相关"是判断,属 L2(commentary_signals 已做 related_policy + theme 匹配)。L1 入库的过滤**极简、纯结构性、账号无关**。

三个分层杠杆,各管各的:

1. **订阅层**(wewe-rss 配置,账号级,**允许 per-account**):砍掉纯噪音号。候选剔除:金杜研究 / 人民网研究院 / 中石油经研院 / 综合开发研究院(样本显示与能源政策零相关)。这是**配置决策**,不是代码补丁,不违反"统一规则"原则。
2. **入库层**(代码,**统一规则,账号无关**):
   - **去重**:`source_url` 已在 vault 或 processed ledger → skip
   - **SKIP(完全丢弃)**:招聘/岗位招募 · 节日快乐/放假通知 · 纯视频(标题 `^视频[：:]` 或正文抓不到文字) · 活动征集/报名通道
   - **market_intel 路由**(结构性信号,非判断)→ staging(不入 vault):`\d+(MW|GWh|GW)` + 中标/开标/采购公告/招标公告 · IPO/上市/融资 · 出货.{0,8}\d+GWh
   - 其余 → vault commentaries(**保守多收**)
3. **相关性判断**:留 L2(commentary_signals)。

> market_intel 暂存:`state/commentary_ingest/market_intel_staging/{YYYY-MM-DD}/{id}.json`,等 B1 完成 market_intel raw schema 后统一迁移。**本线不创建 vault/0_raw/market_intel/**。

---

## 6. 风险缓解(封号 / 反爬 / 节奏)

token 属用户个人微信读书账号,服务器常驻轮询有两层风险面:

| 风险面 | 风险 | 缓解 |
|---|---|---|
| discovery 轮询(wewe-rss→微信 API,带 token) | 轮询太勤 → 微信更快废 token(加重扫码痛)甚至限号 | wewe-rss 轮询间隔设**保守**(数小时/次,如 2–4 次/天),走 wewe-rss `CRON_EXPRESSION` 配置 |
| 正文兜底抓取(→ mp.weixin.qq.com) | 服务器机房 IP 抓微信,反爬风险高 | **优先用 wewe-rss 全文模式,不自己抓**;必须兜底时:限速 + 随机延迟(3–8s)+ 退避重试 + 失败标记不硬刚 |

**核心洞察(写进运营纪律)**:轮询节奏越激进 → 扫码次数越多。保守轮询既防封又减痛。

---

## 7. L1 纪律合规

- **raw 只追加**:只新建 `.md`,不删、不改 vault 已有评论文件
- **LLM 判定不写 immutable raw**:入库 frontmatter 不含任何 LLM 判定字段;`commentary_type` / `business_tag` / `related_policy` **留空**,由 L2 回填(SCHEMA §C 白名单例外)
- **凭据不进 git**:token/路径全 env;`state/commentary_ingest/` 按 `.gitignore` 排除运行时产物
- **幂等**:重复跑结果一致(processed ledger 保证)
- **不写工作中间产物到 vault**:staging/ledger/last_run 全进 `state/`

### 写入 frontmatter(确定性,无 LLM)

```yaml
title:            # feed item title
source_account:   # feed 所属公众号名
source_url:       # https://mp.weixin.qq.com/s/{id}
date_published:   # feed item 发布时间 → ISO date
fetched_at:       # 脚本运行时间
source: wewe-rss
# commentary_type / business_tag / related_policy 留空,L2 填
```

文件名:沿用 vault 现有 title 命名约定,做 title 清洗 + 非法字符替换;碰撞时追加 id 短后缀。

---

## 8. 增量与状态

- **去重主键**:`source_url`(= `mp.weixin.qq.com/s/{id}`),对照 vault 已有文件 frontmatter + `processed_ids.jsonl`
- **processed ledger**:`state/commentary_ingest/processed_ids.jsonl`,每行一个已处理 id + 处置(ingested / skip-junk / market_intel / unprocessable)
- **last_run.json**:本轮拉取数 / 新增数 / 各处置计数 / token 状态 / 时间戳
- **首轮 backlog**:DB 2479 篇是历史积压。首轮全量过一遍(受订阅 curation 收缩后会少很多),之后纯增量

---

## 9. 服务器目录规范(建议)

代码与数据分离,路径不硬编码:

```
/opt/policy-pipeline/        # 代码
  pipeline/                  # 本 git 仓
  docker/                    # compose 文件
/data/policy-pipeline/       # 持久数据
  wewe-rss/                  # wewe-rss 数据卷(SQLite 在此)
  vault/                     # vault 镜像
  state/                     # pipeline 运行时状态
```

wewe-rss compose 数据卷 → `/data/policy-pipeline/wewe-rss:/app/data`。Mac 本地与服务器路径分离,脚本经 env 传入。

---

## 10. 范围之外(明确不做)

- ❌ **扫码自动化(openclaw + IM)**:后续独立 spec。本线只做"检测 token 失效 → 告警",告警即未来该模块的触发接口(seam)
- ❌ **market_intel raw schema(B1)**:本线只暂存,不设计 raw 表示
- ❌ **订阅 curation 的实际执行**:本 spec 给出候选剔除清单,实际在 wewe-rss 配置层操作,不在代码
- ❌ **方向B 换持久源**:对有官网 RSS 的号(RMI/IIGF 等)换源是可并行的后续演进,不在本次
- ❌ **L2 相关性/主题判断**:已有 commentary_signals 负责

---

## 11. 与主 session(service-deploy)的交叉

须知文件:`docs/handoffs/2026-06-07-commentary-ingest-handoff.md`。要点:
- 本线**只新增文件,不改任何已有文件**;不碰 `feat/service-deploy` 分支、不碰 `state/node3c/`
- merge 后由 L1 orchestrator 把 `commentary_ingest` 纳入可调度任务
- docker/wewe-rss/ 可纳入主 compose 或独立

---

## 12. 完成判据(done-gate)

1. `commentary_rss_ingest.py` 能从 wewe-rss feed 拉列表、按 §5 过滤、写 vault(仅追加),幂等可重跑 → **有测试覆盖**
2. feed 缺正文时 trafilatura 兜底链路可用,失败标记不崩
3. `--check-token` 能检出失效并告警(告警通道:webhook/bark/log,可配)
4. market_intel 文章正确进 staging,不污染 vault commentaries
5. `docker/wewe-rss/compose.yml` 含保守轮询间隔,数据卷指向规范路径
6. `state/commentary_ingest/` 产物正确,凭据零泄漏(git 无 token/路径)
   - 写入的评论过 `scripts/audit/validate_schema.py`:已核实 commentary 仅 `title` 必填,本线 6 字段(title/source_account/source_url/date_published/fetched_at/source)全在白名单,留空 LLM 判定字段合规
7. 本机端到端干跑一遍(可用现有失效 token 验证"失效检测"路径;有效路径待用户扫码后验证)
