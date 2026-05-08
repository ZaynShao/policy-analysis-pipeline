---
title: 政策分析 · 当前状态
generated_at: 2026-05-08(C 路径切换初次)
generated_by: scripts/audit/validate_schema.py + 手工补
note: 本文件目标态由脚本自动生成,首版为切换时手工记录
---

# 当前状态(STATUS)

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
- **Legacy drift: 148 条**(全部已在 SCHEMA §F 记录,待 cleanup pass)
  - Policy `tags` + `classification` 倒灌:81 条
  - Commentary 缺 `title`:67 条
  - Commentary 含 reclassified-from-policy 字段:14 条

## 已知缺口

- 64 篇政策(`P_1900_*`)缺 business_view(date 抽不到 → SCHEMA §F 列入 cleanup)
- 6.3% business_view 覆盖缺口(同上)

## 切换状态(C 路径)

- ✓ 工程文件迁出 vault(scripts / audit / staging / handoffs / L2 state)
- ✓ 物理隔离到 `~/政策分析-legacy-archive/`
- ✓ Vault 缩为纯数据仓
- ✓ Pipeline 仓建立 + 反污染纪律 + SCHEMA 契约
- ✓ 第一条 pipeline 脚本(validate_schema.py)跑通,证明契约 work

## 下个版本待办

按优先级:

1. **STATUS 自动化**:写 `scripts/audit/dump_status.py`,从 vault 读数自动生成本文件
2. **Cleanup pass: tags + classification 派生倒灌**:81 篇 policy 含 `tags` + `classification`,迁出到派生层
3. **Cleanup pass: commentary title 补回**:67 篇评论从文件名抽 title
4. **Cleanup pass: reclassified commentary**:14 篇评论删除 policy-only 字段
5. **OPERATIONS.md 蒸馏**:把历史 SOP(已迁 legacy)蒸馏成 300 行内的当前手册
6. **Pipeline 首条数据流**:把一条 L2 派生(关系抽取或 business_view 派生)从 legacy 蒸馏重写
7. **64 篇 P_1900_* 政策的 business_view 补抽**

## 物理位置

| 仓 | 路径 |
|---|---|
| vault(数据) | `~/Documents/Zayn Main/政策分析/` |
| pipeline(工程) | `~/dev/政策分析-pipeline/` |
| legacy archive(历史隔离) | `~/政策分析-legacy-archive/` |
