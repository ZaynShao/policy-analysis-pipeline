# 政策分析 Pipeline

能源政策分析项目的**工程层**。数据(政策 raw、派生产物)住在另一个仓:vault。

```
~/Documents/Zayn Main/政策分析/   ← vault(数据 + SCHEMA.md 副本)
~/dev/政策分析-pipeline/           ← 本仓(工程脚本 + SOP + 状态)
~/政策分析-legacy-archive/         ← 已废弃的旧脚本/产物(物理隔离)
```

## 三层架构

| 层 | 职责 | 落地 |
|---|---|---|
| **L1 采集** | 政策发现 / 抓取 / 入库 / 评论关联 | `scripts/l1_collect/` |
| **L2 派生** | 实体 / 关系 / 评分 / 主题结晶 | `scripts/l2_derive/` |
| **L3 渲染** | 月报 / 决策卡片 / 主题简报 | `scripts/l3_render/` |

## 当前状态

> 详见 `state/STATUS.md`(由 `scripts/audit/dump_status.py` 自动生成)。

## 快速入门

按推荐阅读顺序:

1. **`SCHEMA.md`** — 数据契约。理解 vault 的字段定义。
2. **`CLAUDE.md`** — 反污染纪律。任何在本仓工作的 AI / 人 必读。
3. **`LESSONS.md`** — 建设期踩过的坑。新阶段开始前必读。
4. **`OPERATIONS.md`** — 当前生效的运营手册(SOP 合并版)。
5. **`CHANGELOG.md`** — 本仓的变更记录。

## 为什么分两个仓

历史项目数据与工程混在一个 repo,半年后积累了:
- 27 个 oneshot 脚本
- 11 个 staging 目录
- 30+ 散在 _meta 根的 candidate JSON
- 多份重复的 audit 文件夹
- README / CLAUDE 数字与实际严重不一致

根因是**工程演化污染数据 repo**。本次切分两仓,以 SCHEMA.md 为契约解耦,让两层独立演化。

详细推导见 `LESSONS.md` 与 `docs/`。

## 开发约束

- Oneshot 脚本只能进 `scripts/_oneshot/`,7 天内归档
- 中间产物只能进 `state/`,**不写 vault**
- 文档不引具体路径/脚本名/commit hash(详见 `CLAUDE.md` 反污染纪律)

## License / 性质

内部项目,不开源。
