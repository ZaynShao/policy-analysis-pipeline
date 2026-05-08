---
title: 新 session 启动 brief 模板
purpose: 用户开新 session 接手本项目时,贴这份 brief 作为初始消息
last_updated: 2026-05-08
---

# 新 session 启动 brief

## 用法

每次开新 session 接手本项目工作时,把下面 `## BRIEF 正文` 段贴进新 session 的第一条消息。
不要把当前会话的总结、调试历史、具体老脚本路径贴过去——那会污染新 session。

---

## BRIEF 正文(以下整段贴新 session)

我接手一个能源政策分析项目。它分两个仓:

```
~/Documents/Zayn Main/政策分析/   ← vault(数据 + canonical 配置)
~/dev/政策分析-pipeline/           ← pipeline(工程脚本 + SOP)
~/政策分析-legacy-archive/         ← legacy(已废弃的旧脚本/产物,物理隔离,禁止读)
```

请你 **cd 到 pipeline 仓** 工作:

```
cd ~/dev/政策分析-pipeline
```

启动前**只读以下 3 份文档**(顺序很重要):

1. `CLAUDE.md` — 反污染纪律(读完再继续)
2. `SCHEMA.md` — 数据契约,vault 字段定义
3. `LESSONS.md` — 23 条建设期踩坑沉淀
4. `state/STATUS.md` — 当前状态 + 待办优先级

读完上述后,**不要读** legacy archive 任何内容。所有"以前怎么做"的疑问,只查 LESSONS.md(它已经把原则蒸馏过了)。

---

### 本阶段范围

- **聚焦 L1 完整采集 + L2 高质量派生**
- L3 月报 / 决策卡片**不在范围**
- 既存 vault 数据(1020 政策 / 283 评论 / 956 business_view / 1944 关系边)是真金资产,**不重抓 raw、不全量重跑 L2**

### 我希望你做的事

按 STATUS.md 的优先级:

**P0(L1 完整性)**:
1. **市级政策完整覆盖**——当前只覆盖 ~10 重点城市,要扩到 ~330 全地级市 + 京沪津渝下辖 ~80 区。在 pipeline 仓**新写**渠道扫描脚本(不抄老脚本)。
2. **三类 legacy drift 清理**——SCHEMA §F 记录的 162 条污染。
3. **64 篇 P_1900_\* 缺 date 修复**。

**P1(L2 质量评估)**:
4. **L2 派生质量抽样审计**——9 类关系 / business_view / 主题结晶页各抽 30-50 条校验精度,出 audit 报告。
5. **审计驱动的子集重跑**——精度低的子集才重跑,不全量。

**P2(工程化)**:
6. **STATUS 自动化** — 写 dump_status.py。
7. **OPERATIONS.md 各 Step 蒸馏** — 每 step 5-10 行,不抄老 SOP。

### 关键原则(LESSONS 重点)

1. **Raw immutable** — 0_raw 写完不动,例外见 SCHEMA §C
2. **派生分层** — LLM 生成的不进 raw frontmatter
3. **Schema 是契约** — 字段疑问只查 SCHEMA.md,不 grep 老脚本反推
4. **Oneshot 即归档** — 跑完即移到 `_oneshot/_archived_<date>/`
5. **物理隔离反污染** — 不读 legacy archive

### 我的偏好

- 中文为主,技术词英文
- 先列大框架 todo 再行动
- 多步任务用 TodoWrite 跟进
- 提交节奏:我明确说才 commit,小步可回滚

---

## 模板使用纪律

- **每次新 session 都贴一次完整 brief**(不要假设新 session 知道项目)
- **不要贴当前会话的具体细节**(老 session 走了什么路、踩过什么 bug)— 这些已经在 LESSONS / STATUS 里
- **如果 brief 内容过期了**(比如 STATUS 数字变了),改 STATUS 而不是改 brief
- 这份模板本身在 docs/NEW_SESSION_BRIEF.md,新 session 接手后**第一件事**应该是用最新 STATUS 取代上面的"待办优先级"段

---

## 历史会话提示(给用户自己看)

历史会话曾经做过的事(用户自己参考,**不要贴新 session**):
- 2026-05-08 完成 C 路径切换(双仓解耦)
- pipeline 仓初始化 + L0 骨架
- vault 缩为纯数据仓
- 写 LESSONS.md(23 条原则)
- 写 SCHEMA.md(v1.0 + drift register)
- 第一条管道脚本 validate_schema.py 跑通
