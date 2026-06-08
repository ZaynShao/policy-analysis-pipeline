---
title: 政策分析 · 运营手册(OPERATIONS)
status: v0.3(+ §8 Stage 1 持续上云)
last_updated: 2026-06-08
---

# 运营手册

> 本手册描述**当前生效**的运营流程。历史决策、推导过程、设计思考见 `docs/`。
>
> 所有"上次更新"的数字、覆盖率、批次状态由 `scripts/audit/dump_status.py` 自动生成,**不在本文档手写数字**。

---

## 0. 项目身份

- 服务对象:决策层政策态势把握(L1 完整采集 + L2 高质量派生)
- 数据流:L1 raw → L2 派生
- 工具栈:Tavily / Firecrawl / trafilatura / Claude / wewe-rss / Obsidian

详细背景见 vault 内 `00 背景资料/滴滴能源-政策分析背景.md`(数据/配置类文档,留 vault)。

> **范围说明**:本阶段聚焦 L1 与 L2 的扎实建设。L3 渲染(月报 / 决策卡片)**不在当前阶段范围**。
> Vault 内 `2_crystallized/_reports/` 历史月报产物保留为既存数据,不再维护。

---

## 1. 当前生效流程总图

```
┌──────────────────────────────────────────────────────┐
│ L1 采集(scripts/l1_collect/)                       │
│  ├─ 渠道扫描        Step 2: 渠道目录 + 关键词遍历      │
│  ├─ 标题过滤        Step 3: 规则过滤 + 时间窗校验       │
│  ├─ 三维查重        Step 3.5: URL + 文号 + 标题哈希     │
│  ├─ 抓取暂存        Step 4: Firecrawl/trafilatura 兜底 │
│  ├─ 元数据抽取      Step 4.5: 客观字段 deterministic    │
│  └─ L1 入库         Step 5: 写 vault 0_raw/policies/    │
└──────────────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│ L1 评论(scripts/l1_collect/)                       │
│  ├─ wewe-rss push   持续涌入,自动入库 commentaries     │
│  ├─ 评论反向匹配    B1 文号 / B2 模糊 / B3 LLM         │
│  └─ Tavily 兜底     按分配额未达成时启动               │
└──────────────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│ L2 派生(scripts/l2_derive/)                        │
│  ├─ business_view   Step 5C: LLM 派生评分+影响分析      │
│  ├─ 实体抽取        canonical 匹配                     │
│  ├─ 关系抽取        regex(supersedes/references) +     │
│  │                  启发式(iterates/clarifies/...)+    │
│  │                  LLM(conflicts/cites_basis)        │
│  ├─ derives_from    Step 5C 副产物                     │
│  └─ 主题结晶        2_crystallized/themes/             │
└──────────────────────────────────────────────────────┘

【全程】audit:scripts/audit/ 跑 lint / dedup / status dump
```

---

## 2. SOP 详细步骤

> 此章为骨架,**待从 vault 实际数据 + LESSONS 重新蒸馏**。
>
> 蒸馏原则:每个 step 用 5-10 行说清"输入 / 动作 / 输出 / 异常"。详细推导和设计思考下沉 `docs/`。
>
> **重要纪律**:蒸馏过程不抄 legacy archive 里的老 SOP,只参考 LESSONS.md 的原则与 vault 实际数据形态。

### Step 1 · 去重基线建立
TODO

### Step 2 · 按渠道增量扫描
TODO(覆盖目标:国家级 + 31 省 + **市级全覆盖**,详见 §7 L1 重建任务)

### Step 3 · 标题规则过滤 + 查重
TODO

### Step 3.5 · URL 维度查重
TODO

### Step 4 · 抓取正文到暂存区
TODO

### Step 4.5 · 客观元数据抽取
TODO(关键约束:不做 LLM 业务判断,见 SCHEMA §2 + LESSONS B1)

### Step 5 · L1 入库
TODO(关键约束:frontmatter 白名单,见 SCHEMA §2)

### Step 5C · 业务侧派生
TODO(异步,可缺失,split 写 3 处)

### Step 6 · 评论达成度评估
TODO(Push 主 / Pull 兜底)

### Step 6.5 · 评论→政策反向匹配
TODO(B1/B2/B3 三路)

### Step 7 · 优质公众号识别 + 订阅扩容
TODO

### Step 8 · 缺口分析 + 反哺渠道目录
TODO

---

## 3. 执行节奏

### 维护期(目标态)
| 模式 | 触发 | 跑哪几步 |
|---|---|---|
| 每日 cron | 9:00 | Step 1-5 增量 + Step 6 仅 ≥3 分 |
| 每周 cron | 周日 10:00 | Step 7-8 |
| 频道推送 | 用户贴 URL | Step 4-5 |

### 当前状态
- 维护期 cron 未启用
- 各 step 由人工触发 pipeline 脚本

---

## 4. 关键参数

| 参数 | 维护期默认 | 说明 |
|---|---|---|
| 时间窗 | 24h | Step 2 增量 |
| 翻页硬上限 | 5 页 | Step 2 兜底 |
| 边际效益阈值 | 连续 3 页新增 <10% 停 | Step 2 |
| Jaccard 去重阈值 | 0.85 | Step 2 |
| 评论触发阈值 | ≥3 分 | Step 6 |

---

## 5. 兜底链路

```
Step 4 抓取(政策正文):
  Firecrawl 首选(质量高 + PDF 支持)
    └─ 失败/无额度 → Tavily search 找 URL
                       └─ Python requests + trafilatura 提取
                            └─ trafilatura 抽不到 → BeautifulSoup 兜底全文清洗
                                 └─ 仍失败 → 标 fetch_error,人工

Step 6 抓取(评论正文): 同上链路
```

实测对比与具体配置详见 `LESSONS.md` B3 + `docs/tooling/`。

---

## 6. 常见异常与应对

| 情况 | 应对 |
|---|---|
| Tavily / Firecrawl 超限 | 跑到哪断到哪,写断点 JSON,下轮 resume |
| 正文是摘要而非原文 | 标 `confidence: 0.6`,Step 5 降档 |
| 一个政策多渠道首发 | 取发布日期最早者为主,其他作 `sources` 数组存 |
| 打分争议大(2 次差 ≥2) | 落人工审核清单,暂不入库 |
| PDF 解析失败 | `pdftotext` 兜底;仍失败标 `fetch_error` |

---

## 7. L1 重建 / L2 评估任务(当前阶段重点)

本阶段不出月报,聚焦 L1 + L2 扎实。具体任务见 `state/STATUS.md` 的"待办"段。核心任务:

### L1 任务

1. **市级政策完整覆盖**(从"部分城市"扩到"全市级"):
   - 当前覆盖:13 部委 + 31 省 + ~10 个重点城市
   - 目标:所有地级市(~330 个)的发改委 / 能源局 / 政府网三主线模板化扫描
   - 包含:京沪津渝下辖区(~80 区)单独扫
   - 不要求一次跑完,要求**有完整的市级渠道清单 + 优先级机制**
   - 负责脚本:`scripts/l1_collect/run_step2_to_5.py`(待写)

2. **三类 legacy 污染清理**(基于 SCHEMA §F 的 cleanup pass):
   - Policy `tags` + `classification` 倒灌:81 篇
   - Commentary 缺 `title`:67 篇
   - Commentary reclassified-from-policy 残留:14 篇
   - 负责脚本:`scripts/_oneshot/cleanup_*.py`(跑完即归档)

3. **64 篇 P_1900_* 缺 date 修复**:从正文/URL 重抽 date,补 business_view

### L2 任务

1. **L2 派生质量抽样审计**:
   - 9 类关系各抽 30-50 条,人工/LLM 校验精度
   - business_view 抽 30-50 条,校验"影响分析"业务对齐度
   - 主题结晶页抽 3-4 个,校验"政策聚合是否合理"
   - 负责脚本:`scripts/audit/sample_l2_quality.py`(待写)

2. **审计结果决定子集重跑**:
   - 精度 ≥95%:接受,不重跑
   - 精度 80-95%:列待修订清单,人工 + LLM 联合修
   - 精度 <80%:该子集重跑(用新 prompt + 当前 vault 数据)

### 范围之外(本阶段不做)

- ❌ L3 月报渲染
- ❌ 重抓 raw(老 raw 是资产,不可重抓)
- ❌ 全量重跑 L2(成本不可行,且大概率结果相似)
- ❌ 在老脚本基础上 patch(本阶段所有脚本在 pipeline 仓**新写**)

---

## 8. Stage 1 持续上云(云端投影 · 2026-06-08 上线)

> producer 产 vault → push GitHub → 东京服务器每天定时 `git pull`(变了才拉)→ 容器 `run_sync` 投影到 heng-pg。告别手动 rsync + 手动 sync。设计见 `docs/superpowers/specs/2026-06-08-stage1-continuous-sync-design.md`,计划见对应 plan。

### 8.1 数据流

```
Producer(Mac/国内常开机)产 vault → git commit + push
        │
        ▼  GitHub: ZaynShao/energy-policy-analysis(vault 仓·main)
        │
东京服务器 ── host cron 每天 21:00 ──▶ scripts/service/sync_tick.py
        │   git fetch --depth=1;HEAD 变了才 git reset --hard
        │   → docker compose run --rm policy-pipeline  python -m scripts.sync.run_sync
        │   → 投影 heng-pg(staging:hengguan_staging / 生产:hengguan)
        └── Mac 只读阅览 ── git pull ──▶ Obsidian 看最新
```

### 8.2 服务器实测布局(≠ 早期设计假设,以此为准)

| 项 | 路径 |
|---|---|
| pipeline 代码 | `/root/policy-pipeline-src` ⚠️ **非 git 仓**(tarball 部署;sync_tick.py 经 scp 落地) |
| vault | `/root/policy-vault`(git 仓·deploy key `github-vault`) |
| state | `/root/policy-pipeline-state`(含 `last_sync_run.json`) |
| 环境变量 | `/etc/policy-pipeline/pipeline.env`(含 DATABASE_URL,**out-of-git**) |
| compose | `/root/policy-pipeline-src/docker-compose.server.yml`(挂 vault:ro + state;net `safety-platform_platform-net`) |
| 日志 | `/var/log/policy-pipeline/sync_tick.log`(logrotate weekly×4) |

### 8.3 日常运维

- **自动**:cron `0 21 * * *`(producer 当天产完后)。查 `crontab -l`。
- **手动跑一次**:
  ```bash
  cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.sync_tick \
    --vault-dir /root/policy-vault --pipeline-dir /root/policy-pipeline-src \
    --compose-file /root/policy-pipeline-src/docker-compose.server.yml
  ```
  无变更 → `no change, skip`(不空跑);有变更 → reset + run_sync。
- **看结果**:`cat /root/policy-pipeline-state/last_sync_run.json`(synced/relation/errors/skipped_invalid)+ `tail /var/log/policy-pipeline/sync_tick.log`。
- **失败可见(过渡期)**:run_sync 退出码 + `last_sync_run.json` 的 `errors` 非空 + 日志。**正式告警 = hengguan 内建"消息"/Notification(配套 PR,待建)**。

### 8.4 vault rsync→git 一次性切换(已于 2026-06-08 完成 · 回滚锚)

切换步骤(`mv` 备份 → 浅克隆):
```bash
mv /root/policy-vault /root/policy-vault.rsync-bak-$(date +%s)
git clone --depth=1 git@github-vault:ZaynShao/energy-policy-analysis.git /root/policy-vault
```
**回滚**:`rm -rf /root/policy-vault && mv /root/policy-vault.rsync-bak-* /root/policy-vault`
deploy key:服务器 `~/.ssh/vault_deploy`(只读)+ `~/.ssh/config` 的 `Host github-vault`;公钥加在 vault 仓 Deploy keys(read-only)。

### 8.5 staging → 生产 cutover(gated · 不在 Stage 1)

`pipeline.env` 当前 `DATABASE_URL` 指 `hengguan_staging`。切生产 = **PR #14 合并 + pg_dump 备份 + migrate deploy + TRUNCATE + 改 DATABASE_URL→hengguan + 首 sync**,单独 gated,双确认。cron 不变,自动续上生产。

### 8.6 已知 caveat

- **代码漂移**:`/root/policy-pipeline-src` 是非 git tarball,且其中 L2 常驻服务代码(`run_l2`/`orchestrate`/…)**未在 pipeline git 仓**。服务器一挂即丢。修复 = 后续"代码 git 化部署"(路 B / Stage 1.5)。
- **upsert 不 prune**:run_sync 只 upsert,不删 vault 已移除的政策。生产 cutover 先 TRUNCATE 拿干净基线;staging 长期累积无害。
- **producer 不常开(现 Mac)**:Mac 不开不 push,服务器当天拉不到新 → 迁国内常开机后消失。

### 8.7 上线验证记录(2026-06-08)

E2E 实测:模拟 vault 落后一提交 → sync_tick 检测 `cf2f824f→c7389b10` → reset → run_sync → **synced 761 / relation 998 / errors=[] / exit 0**;无变更再跑 → `no change skip`。HEAD 比对幂等、cron/日志/logrotate、deploy key 只读拉取全部验过。

---

## Changelog

### v0.3 — 2026-06-08
- 添 §8 Stage 1 持续上云(vault rsync→git、sync_tick cron、实测布局、cutover 指针、caveat、验证记录)

### v0.2 — 2026-05-08
- 删 L3 月报章节(本阶段不做)
- 添 §7 L1 重建任务清单(含市级完整覆盖)
- 范围说明:聚焦 L1 + L2 扎实

### v0.1 — 2026-05-08
- 骨架建立
- 总图 + 执行节奏 + 兜底链路 + 异常应对从历史 SOP 抽出
