---
title: 政策分析 · 当前状态
generated_at: 2026-05-08(C 路径切换初次)
generated_by: scripts/audit/validate_schema.py + 手工补
note: 本文件目标态由脚本自动生成,首版为切换时手工记录
---

# 当前状态(STATUS)

## 本阶段范围

聚焦 **L1 完整采集 + L2 高质量派生**,**L3 渲染(月报 / 决策卡片)不在范围**。
既存 vault `2_crystallized/_reports/` 历史月报作为数据保留,不再更新。

---

## Vault 数据规模

| 维度 | 数字 |
|---|---:|
| L1 政策(`0_raw/policies/`)| **1020** |
| L1 评论(`0_raw/commentaries/`)| 283 |
| L2 business_view 覆盖 | **956 / 1020 (93.7%)** |
| L2 关系边(active,9 类)| 1944 |
| L2 主题结晶页 | 13 主题 |

## L2 关系细分

| 类型 | 边数 |
|---|---:|
| derives_from | 677 |
| references | 446 |
| cites_basis | 384 |
| aligns_with | 192 |
| clarifies | 113 |
| iterates | 58 |
| extends | 37 |
| supersedes | 7 |

## SCHEMA 契约符合度

最近一次跑(2026-05-08 C 路径切换):

- **严格违反: 0 条** ✓
- **Legacy drift: 148 条**(全部已在 SCHEMA §F 记录)

---

## L1 采集覆盖现状

| 层级 | 当前覆盖 | 目标 | 缺口 |
|---|---|---|---:|
| 国家级(13 部委) | ✓ 已覆盖 | 维持 | 0 |
| 省级(31 省) | ✓ 已覆盖 | 维持 | 0 |
| 13 主题 × 31 省矩阵 | 60.5%(244 cells) | 收益递减区,不强求 | ~159 cells(可接受) |
| **市级(地级市)** | **~10 重点城市** | **全 ~330 个地级市** | **~320 城市** |
| 直辖市下辖区(京沪津渝) | 0 | ~80 区 | ~80 区 |
| 一般地级市下辖区/县 | 0 | 不强求 | — |

**核心缺口:市级覆盖严重不足**——这是本阶段 L1 重建的主目标之一。

---

## 已知数据问题

### Legacy drift(148 条,SCHEMA §F 记录)
- Policy `tags` + `classification` 倒灌:81 条
- Commentary 缺 `title`:67 条
- Commentary 含 reclassified-from-policy 字段:14 条

### 其他缺口
- 64 篇政策(`P_1900_*`)缺 business_view(date 抽不到)
- 6.3% business_view 覆盖缺口(同上)
- B2 标题模糊匹配 ~130 条精度未校验就入 raw frontmatter

---

## 切换状态(C 路径)

- ✓ 工程文件迁出 vault(scripts / audit / staging / handoffs / L2 state)
- ✓ 物理隔离到 `~/政策分析-legacy-archive/`
- ✓ Vault 缩为纯数据仓
- ✓ Pipeline 仓建立 + 反污染纪律 + SCHEMA 契约
- ✓ 第一条 pipeline 脚本(validate_schema.py)跑通

---

## 待办(本阶段重点)

### 优先级 P0 — L1 完整性

#### T1 · 市级政策完整覆盖
- 目标:从"~10 重点城市"扩到"~330 全地级市"+ 京沪津渝下辖 ~80 区
- 方法:在 pipeline 仓**新写**(不抄老脚本)市级渠道扫描脚本
  - 输入:省级行政区划代码表 + 市级渠道目录模板("市发改委 / 市能源局 / 市政府网"四字段)
  - 输出:市级 candidate jsonl,经 Step 3-5 入 raw
- 优先级机制:业务驱动(滴滴覆盖城市优先)+ 反哺驱动(评论引用过的城市优先)
- 不强求一次跑完,要**有完整渠道清单 + 优先级机制**就算交付
- 时间预算:2-3 天

#### T2 · Legacy drift 三类清理
- T2a · Policy `tags` + `classification` 倒灌(81 篇)→ 迁出到派生层
- T2b · Commentary 缺 `title`(67 篇)→ 从文件名抽 title 补回
- T2c · Commentary reclassified 残留(14 篇)→ 删 policy-only 字段
- 时间预算:每类 1-2 小时,共半天

#### T3 · 64 篇 P_1900_* 缺 date 修复
- 从正文/URL/H1 重抽 date,补 business_view
- 时间预算:1-2 小时

### 优先级 P1 — L2 质量评估

#### T4 · L2 派生质量抽样审计
- 9 类关系各抽 30-50 条人工/LLM 校验精度
- business_view 抽 30-50 条校验"影响分析"业务对齐度
- 主题结晶页抽 3-4 个校验聚合合理性
- 输出 audit 报告 → 决定哪些子集需要重跑
- 时间预算:1-2 天

#### T5 · 审计驱动的子集重跑
- 精度 ≥95%:接受,不重跑
- 精度 80-95%:列待修订清单,人工 + LLM 联合修
- 精度 <80%:该子集重跑
- 时间预算:依审计结果,1-3 天

### 优先级 P2 — 工程化

#### T6 · STATUS 自动化
- 写 `scripts/audit/dump_status.py`,从 vault 读数自动生成本文件
- 时间预算:1-2 小时

#### T7 · OPERATIONS.md 各 Step 蒸馏
- 把 LESSONS 与 vault 实际数据形态结合,各 step 写 5-10 行
- 不抄 legacy 老 SOP
- 时间预算:半天到 1 天

---

## 范围之外(本阶段不做)

- ❌ L3 月报渲染
- ❌ 决策卡片 / 主题简报
- ❌ 重抓 raw(老 raw 是资产,不可重抓)
- ❌ 全量重跑 L2(成本不可行,且大概率结果相似)
- ❌ 在 legacy 老脚本基础上 patch(本阶段所有脚本在 pipeline 仓**新写**)

---

## 物理位置

| 仓 | 路径 |
|---|---|
| vault(数据) | `~/Documents/Zayn Main/政策分析/` |
| pipeline(工程) | `~/dev/政策分析-pipeline/` |
| legacy archive(历史隔离) | `~/政策分析-legacy-archive/` |
