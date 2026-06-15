# Runbook：存量 raw "发文日误标" 回填(date/id 再解析)

**状态(2026-06-15)**:抽取层机制已修+全绿;回填 oneshot 已写+测试全绿;已对真 vault(本地 1241 篇)跑 dry-run 并人工核样。**未 apply**(写 vault 经操作者)。

## 背景

L1 `date` 系统性把"生效/截止/执行起始日"写进 `date`(而非发文/印发/落款日),按月过滤漏政策(2026-05 月刊 L-cov 查漏发现)。根因=首匹配+无语义,横跨 L1 抽取 / L2 落款 / resolver 护栏三层。已修(见 PR/commit)。

## 机制(单一真相源)

`scripts/l1_collect/cn_dates.py`:剔除生效/截止候选、识别中文数字落款、剔除 trafilatura `采集` 页脚与 `X日前` 任务截止;`pick_luokuan_strict` 只采信"机关名/发布日期标签/中文数字"背书的高置信落款(回填覆盖存量用)。L1 `extract_date`/`extract_official_number`、L2 `extract_luokuan_date`、`resolver` 均复用。

## 回填脚本

`scripts/_oneshot/date_issuance_backfill.py`——扫 `0_raw/policies/` 全量,确定性决策:

- **自动修**:cur_date 可证为错(生效/截止误标、未来年、破损/占位)**且**抽到高置信落款 → 改 date(§C 审计:`provenance.date_fixed_*`)。年份变则重算 id(旧 id 入 aliases,`id_fixed_*`)。
- **入队**:错但抽不到可信落款 → `state/date_backfill/queue.jsonl` 人工裁。
- **不动**:合理且非误标的 date(哪怕落款不同)→ 信任(误伤≈零)。发文日==生效日(同日既落款又生效)归此类。
- **official_number**:不在 SCHEMA §C 白名单 → 只标记待复核,**不写**。

```bash
VAULT="$HOME/Documents/Zayn Main/政策分析"
python3 scripts/_oneshot/date_issuance_backfill.py --vault "$VAULT"             # dry-run + HTML 报告
python3 scripts/_oneshot/date_issuance_backfill.py --vault "$VAULT" --show-diff
python3 scripts/_oneshot/date_issuance_backfill.py --vault "$VAULT" --apply      # 写 raw(仅文件;commit/push 见下)
```

## Dry-run 结果(2026-06-15,1241 篇)

| 桶 | 数量 | 说明 |
|---|---|---|
| 自动修 · 同年只改 date | 33 | **无 id 变,无派生级联,安全** |
| 自动修 · 跨年改 date+id | 10 | id 变,每篇有 5–22 处派生引用(business_view/relations/summaries/themes)→ **需配套派生重指** |
| 入队人工 | 17 | 错但无可信落款(如咨询互动时间戳) |
| official_number 待复核 | 19 | 只标记不写 |

三篇证据政策均正确:ZJ `2026-07-01→2026-05-28`、BJ `2026-12-31→2026-03-18`、NDRC `2027-01-01→2023-09-01`(id→`P_2023_NDRC_572b0ea8`)。

## Apply 纪律(红线)

- **dry-run 先行 + 人工核样**(已做)。
- apply 写本地 vault raw(§C 就地,可逆,vault git 跟踪)。**commit/push 经 `scripts/service/produce_and_push.run(vault, ["0_raw/policies/"], msg)`,凭据/push 由操作者**。
- **同年 33**:无级联,可先 apply+push。
- **跨年 10**:id 变 → 必须**另跑派生层重指 oneshot**(模型 `t3_phase3_remap_derivatives`),**不与 raw 改动同 commit**(SCHEMA §C)。未做重指前不要单独 push raw id 改动。
- **official_number 自动改**:需先走 SCHEMA §C 修订提案(扩白名单),当前只标记。

## 闭环剩余

1. apply 同年 33(+produce_and_push push)。
2. 跨年 10:raw id 改 + 派生重指(配套),分步。
3. queue 17 / official_number 19:人工 / §C 决策。
4. 新抽取层部署到 VPS(管以后新入库)——经操作者。
