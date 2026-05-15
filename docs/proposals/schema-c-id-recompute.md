---
title: SCHEMA §C 新增条目 proposal · id 重算白名单
status: MERGED into SCHEMA.md v1.1 on 2026-05-12
proposed_by: T3 任务驱动(P_1900 id drift 修复)
proposed_at: 2026-05-08
target_schema_version: v1.1
merged_at: 2026-05-12
---

# Proposal:SCHEMA §C 加一条 id 重算白名单

## 背景

T3 任务发现 vault 现状中有 112 篇 policy 的 frontmatter `id` 字段仍为 `P_1900_*`,但其中 ≥111 篇的 `date` 字段已是合理日期(部分历史上跑过 `date_fixed_method: url_path_pattern` 修过)。**date 修了,id 没跟着重算**,造成 deterministic 派生身份与实际元数据脱钩。

类似的"事后修补 raw frontmatter 的 deterministic 字段"早已实质存在:

- `provenance.date_fixed_at` / `date_fixed_method` / `date_fixed_from`
- `provenance.region_fixed_at` / `region_fixed_method` / `region_fixed_from`
- `provenance.issuer_fixed_at` / `issuer_fixed_method` / `issuer_fixed_from`

vault 当前数据里这些字段已经存在(SCHEMA §F drift register 也登记了部分),但 SCHEMA §C 没有给它们对应的白名单条目——它们处于"实际允许、文档未授权"的灰区。

T3 现在需要做的"id 重算"与上述事后修补**性质完全相同**:都是 deterministic 派生身份字段(date / region / issuer / id),都不是 LLM 自由文本,都从已有 metadata 计算得出。

按 LESSONS A4("边界例外要白名单化")和 E2("边界例外是糟糕设计的信号——出现例外时先反思原则是否切错"),这次反思后的判断:

- 原则切对了:Raw 不可变保护的是**业务语义**(LLM 摘要、影响分析、评分等)
- 例外定义不准:**deterministic 身份字段**(id / date / region / issuer)既不是业务语义,又必须随源数据修正而更新,本来就该在白名单里

## Proposal

### A · SCHEMA §C 新增子节

在 `## C. Raw 不可变的边界例外(白名单)` 节内,在现有 "Commentary 关系字段" 之后新增一个子节:

```markdown
### Deterministic 身份字段重算

允许 pipeline 重算并就地更新以下字段(仅当新值由确定性规则从已有 metadata 计算得出,**不**是 LLM 自由生成):

- `id`(由 `date.year` + `issuer_canonical` + `official_number/hash` 计算)
- `aliases`(随 `id` 同步更新,**旧 id 必须保留在 aliases 数组中**以保持 Obsidian 反链可解)
- `date`(从 URL path / 正文 / H1 等结构化位置抽取)
- `region.level` / `region.code` / `region.name`(由 `issuer_canonical` 或 URL 域名 lookup)
- `issuer` / `issuer_canonical`(由 URL 域名 / 正文 H1 抽取后查 canonical 表)

每次重算必须在 `provenance` 中记录审计字段:

- `<field>_fixed_at`(ISO 时间戳)
- `<field>_fixed_method`(规则类别,枚举:`url_path_pattern` / `body_extract` / `title_extract` / `domain_lookup` / `id_recompute_from_metadata` / `combined`)
- `<field>_fixed_from`(原值)
- `<field>_fix_confidence`(0–1,可选)

对 `id` 字段额外要求:

- 重算后 frontmatter `aliases` 数组**必须**同时包含旧 id 和新 id
- 文件名保留不变(vault 文件名是中文标题哈希,与 id 解耦)
- 派生层引用旧 id 的位置由专用 oneshot 同步重指(不与 raw 改动同 commit)
```

### B · §F drift register 删除冗余条目

将 §F 中以下 drift 条目移除(因它们已被新白名单覆盖):

- `provenance.date_fixed_*`(若存在)
- `provenance.region_fixed_*` / `provenance.issuer_fixed_*`(若存在)

(注:§F 中 `audit_run` / `candidate_priority` / `src_count` 等审计派生字段保留 drift 状态,这一类不是身份字段。)

### C · Changelog 条目

```markdown
### v1.1 — 2026-05-08(身份字段重算白名单)
- §C 新增 "Deterministic 身份字段重算" 子节,显式授权 id/date/region/issuer 在确定性规则下就地重算
- §F 移除已被新白名单覆盖的修复字段 drift 条目
- driver: T3 P_1900 id drift 修复任务,详见 pipeline `state/T3/p1900_inventory.md`
```

## 边界(本 proposal **不**做的事)

- **不**允许 LLM 自由生成 raw frontmatter 字段(LLM 派生仍走派生层,A3 不动)
- **不**允许在 raw body 内编辑(§0 + §2 不动)
- **不**给 commentary 关系字段以外的 LLM 派生字段开后门
- **不**减少现有 §C 已写明的 commentary 关系字段白名单

## 影响评估

| 项 | 影响 |
|---|---|
| Raw immutable 哲学 | 收紧:把"实际允许、文档未授权"的灰区收编为正式白名单,反而比现状更明确 |
| 派生层依赖 | 不变:派生层只读"目标"字段,不读 legacy(§F 处置纪律 4) |
| Obsidian 反链 | 不破坏:旧 id 留在 aliases,`[[P_1900_*]]` 仍能解析 |
| Validator 实现 | 需要在 `validate_schema.py` 加对 `*_fixed_*` provenance 子键的容忍逻辑(已存在) |
| 日后再发现身份字段错 | 直接重算,审计字段更新版本号(`<field>_fixed_at` 时间戳即版本) |

## 决策项

- [ ] 同意 A 节(新增白名单子节)
- [ ] 同意 B 节(§F 删除冗余 drift 条目)
- [ ] 同意 C 节(changelog 写入 v1.1)
- [ ] 用词修订:                 (留空表示无)
