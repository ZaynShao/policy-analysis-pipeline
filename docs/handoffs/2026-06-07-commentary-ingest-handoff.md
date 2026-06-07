# 须知：commentary-rss-ingest 线 → 主 session（service-deploy）

**分支**：`claude/zen-saha-c3ac3c`  
**功能**：wewe-rss → vault 自动入库闭环（L1 commentary 采集管道）

---

## 新增文件（不修改任何已有文件）

```
scripts/l1_collect/commentary_rss_ingest.py   # 入库主脚本
docker/wewe-rss/compose.yml                   # wewe-rss 服务定义
state/commentary_ingest/.gitkeep              # 状态目录（gitignore 大部分内容）
```

## 不碰的路径（声明）

- `scripts/l1_collect/` 其他所有文件：只读、不改
- `vault/0_raw/policies/`：不写
- `vault/0_raw/commentaries/`：仅追加，不删、不改已有
- `vault/0_raw/market_intel/`：**不创建**（B1 未完成，market_intel 原始文章暂存 `state/commentary_ingest/market_intel_staging/`，等 B1 设计）

## 与 service-deploy 线的交叉点

| 交叉点 | 说明 | 行动建议 |
|---|---|---|
| L1 服务编排 | service-deploy 的 L1 orchestrator 需感知 commentary_rss_ingest 作为一个可调度任务 | merge 后在 orchestrator 的任务清单里加一条 `commentary_ingest` |
| docker/wewe-rss/ | 本线新增，service-deploy 可按需纳入主 compose 或保持独立 | 建议纳入，共享网络 + 统一日志 |
| state/ 目录结构 | 本线写 `state/commentary_ingest/`，service-deploy 已有 `state/` 用法 | 无冲突，各自子目录 |
| vault 路径 | 本线只写 `0_raw/commentaries/`，与 service-deploy 的 policy 采集路径不重叠 | 无冲突 |

## market_intel 暂存说明

wewe-rss 订阅中 4 个账号的文章被 **title 规则**（非账号规则）识别为 market_intel：
中标/开标/采购公告、出货量/GWh/融资额等数值型行情标题。

这些文章写到 `state/commentary_ingest/market_intel_staging/{YYYY-MM-DD}/{filename}.json`，
格式与 commentary 相同但不写 vault，**等 B1 完成 market_intel raw schema 设计后统一迁移**。

## merge checklist

- [ ] orchestrator 任务清单加 `commentary_ingest` 条目
- [ ] docker compose 决定是否纳入 wewe-rss 服务
- [ ] 确认 `/data/policy-pipeline/wewe-rss/` 服务器路径符合部署规范
