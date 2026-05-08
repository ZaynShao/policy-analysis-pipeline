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
