# 须知：commentary-rss-ingest 线 → 主 session（service-deploy）

**分支**：`claude/zen-saha-c3ac3c`
**功能**：wewe-rss → vault 自动入库闭环（L1 commentary 采集管道）
**spec**：`docs/superpowers/specs/2026-06-07-commentary-rss-ingest-design.md`

---

## 部署位置（关键，避免误解）

本线**跑国内节点**（先 Mac，后续迁国内容器），**不在东京服务器跑、不在东京服务器写 vault**。
原因：token 是用户个人微信读书账号，东京机房 IP 会触发微信地理风控（最坏冻结账号）。详见 spec §6.1。

评论写 **Mac vault** `0_raw/commentaries/`，经**现有 Mac→东京 rsync** 流上 `/root/policy-vault`，
服务器侧只读消费 → **与 service-deploy 的单向镜像模型零冲突**。

## 新增文件（基本不改已有文件，一处例外见下）

```
scripts/l1_collect/commentary_rss_ingest.py          # 入库主脚本（阶段一）
docs/runbooks/commentary-rss-ingest-migration.md     # Mac→国内容器迁移文档（阶段二）
docker/wewe-rss/compose.yml                           # 容器定义（阶段二迁移用）
state/commentary_ingest/.gitkeep                      # 状态目录（gitignore 大部分内容）
```

**一处对已有文件的追加**：项目根 `CLAUDE.md` 追加"评论 RSS 迁移方法摘要"（用户要求维护进 CLAUDE.md）。
→ 这是与 service-deploy 唯一可能 merge 撞车点，主 session 注意。

## 不碰的路径（声明）

- `feat/service-deploy` 分支、`state/node3c/`、服务器 `/root/safety-platform`：**完全不碰**
- `scripts/l1_collect/` 其他所有文件：只读、不改
- `0_raw/policies/`：不写
- `0_raw/commentaries/`：仅追加，不删、不改已有
- `0_raw/market_intel/`：**不创建**（B1 未完成，market_intel 文章暂存 `state/commentary_ingest/market_intel_staging/`）
- 东京 `/root/policy-vault`：**本线不写**（只经 rsync 间接流入）

## 与 service-deploy 线的交叉点

| 交叉点 | 说明 | 行动建议 |
|---|---|---|
| 部署位置 | 本线国内节点，service-deploy 在东京服务器 | 无冲突，物理分离 |
| vault 写入 | 本线写 Mac vault `0_raw/commentaries/`，经现有 rsync 上服务器 | 无冲突，单向镜像不变 |
| L1 编排 | 本线是国内 cron 任务，非东京 orchestrator 的可调度项 | 东京 orchestrator **不需**纳入本线 |
| state/ 目录 | 本线写 `state/commentary_ingest/` | 无冲突，各自子目录 |
| CLAUDE.md | 本线追加迁移方法摘要 | merge 时注意此文件 |

## market_intel 暂存说明

wewe-rss 订阅中 4 个账号的文章被 **title 规则**（非账号规则）识别为 market_intel：
中标/开标/采购公告、出货量/GWh/融资额等数值型行情标题。

这些文章写到 `state/commentary_ingest/market_intel_staging/{YYYY-MM-DD}/{id}.json`，
格式与 commentary 相同但不写 vault，**等 B1 完成 market_intel raw schema 设计后统一迁移**。

## merge checklist

- [ ] 确认 CLAUDE.md 追加段无冲突
- [ ] 确认本线 state 子目录与 service-deploy 无重叠
- [ ] （阶段二）国内容器节点定下后，按迁移文档迁移
