# Pipeline 变更日志

## 0.1 — 2026-05-08(初始化)

C 路径切换:从原 vault 单仓拆出工程层,本仓为新生工程层。

**带过来的**:
- 数据契约(SCHEMA.md)— 从历史 schema 蒸馏 + 对齐当前 vault 实际产出
- 踩坑沉淀(LESSONS.md)— 23 条原则,5 个章节
- 反污染纪律(CLAUDE.md)— 5 条工程仓约束
- 运营手册骨架(OPERATIONS.md)— 待逐步填实

**有意没带过来的**:
- 历史 oneshot 脚本(物理隔离到 ~/政策分析-legacy-archive/)
- 历史 audit / handoff / staging(同上)
- 中间产物(同上)

**跟 vault 的接口**:
- vault 路径:`~/Documents/Zayn Main/政策分析/`
- vault 内 SCHEMA.md 与本仓 SCHEMA.md 同步
- pipeline 通过 SCHEMA 校验脚本读写 vault

**未完成事项(下个版本)**:
- 蒸馏 OPERATIONS.md 各 step 详细内容
- 写第一条 pipeline 管道脚本(L2 关系抽取)验证 schema 契约
- 写状态自动生成脚本 `scripts/audit/dump_status.py`
- 补 64 篇 P_1900_* 政策的 business_view(date 抽不到)

## 0.2 — 2026-05-08(范围调整)

- **删 L3 月报范围**:本阶段聚焦 L1 + L2,不出月报
  - OPERATIONS.md:删月报章节,新增 §7 L1 重建任务
  - SCHEMA.md:`2_crystallized/_reports/` 标"暂不维护"
  - README.md:架构层表格 L3 标"暂不维护"
  - 删 `scripts/l3_render/` 空目录
- **明确 L1 重建主目标**:市级政策从 ~10 重点城市扩到 ~330 全地级市 + 京沪津渝下辖区
- **新 session 启动 brief 模板**:`docs/NEW_SESSION_BRIEF.md`,用户开新 session 时直接贴
- **STATUS 重写**:本阶段范围 / L1 覆盖现状(分级别)/ 优先级 P0-P2 待办

## 0.3 — 2026-05-12(T2 + T3 完成)

P0 任务里 T2 (drift 清理) + T3 (P_1900 id 修复) 全部完成。T1 (市级覆盖) 仍待开。

**SCHEMA 演进**:
- v1.1:§C 新增 "Deterministic 身份字段重算" 白名单(`id` / `aliases` / `date` / `region` / `issuer`),驱动来自 T3 的 P_1900 id drift 修复
- proposal 文档归档:`docs/proposals/schema-c-id-recompute.md`(status: MERGED)

**T3 · P_1900 id drift 修复**:
- 实际 112 篇(STATUS 旧值 64 不准),分 4 类 A/B/C/D
- A 类 28 篇 archive 到 `_archive/policies/t3_a1_classifier_drops_2026-05-08/`(classifier 标记的低质数据)
- B 类 62 篇 date 重抽 + id 重算(31 篇 URL 抽到精确日,其余分级 fallback)
- C 类 21 篇仅 id 重算(date 本就对)
- D 类 1 篇留 backlog
- 派生层同步重指:business_view 72 rename + 22 archive / policy_summaries.jsonl 72 + 22 / relations 7 类 210 + 3
- aliases 保留旧 id,Obsidian 反链不破坏
- Vault 主目录 P_1900 从 112 → 1

**T2 · Legacy drift 三类清理**:
- T2a 51 篇 policy → 把 `tags` + `classification` 迁到新派生层 `1_extracted/policy_classification.jsonl`
- T2b 53 篇 commentary → 从文件名补 `title`
- T2c 14 篇 commentary → 删 reclassified 残留(id / issuer / region / tags / _migrated_* 等)

**新增脚本**(全部 dry-run + apply 模式):
- `scripts/audit/dump_p1900_inventory.py` — P_1900 4 类分类报表
- `scripts/audit/dump_t2_inventory.py` — T2a/T2b/T2c 精确数字
- `scripts/_oneshot/t3_phase{1,2a,2b,3}_*.py`
- `scripts/_oneshot/t2{a,b,c}_*.py`

**新增文档**:
- `docs/proposals/schema-c-id-recompute.md`(MERGED)
- `state/T3/upstream_backlog.md`(抓爆 / SEO 攻击 / D 类残留等上游问题登记)
- `state/T3/*` 和 `state/T2/*` apply 日志

**LESSONS 实例化**:
- C5(数字必须脚本生成):STATUS 旧值 64/81/67 与实际 112/51/53 出入显著,推动 inventory 脚本化
- A4(边界例外要白名单化)+ E2(例外是糟糕设计信号 → 反思原则):身份字段重算正式纳入 SCHEMA §C,而非默默扩张
- B3(兜底链路)缺口:T3 archive 28 篇中有 2 篇是"抓爆"(只剩 footer),登记到上游 backlog

**未完成**:
- T1 市级覆盖(P0,本节未动)
- D 类 1 篇 P_1900_SX_caf8e7eb date 真空
- business_view 重跑 + coverage 重测
- T4-T7(P1/P2,本节未动)
