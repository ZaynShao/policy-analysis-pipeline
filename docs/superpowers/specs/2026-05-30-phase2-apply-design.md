---
title: 设计 spec · ①源到位 Phase-2(apply,改 raw)
date: 2026-05-30
status: 待用户复核本 spec 后再 build
node: ①源到位 的"应用"半边(dry-run 已 merge 到 main)
charter: docs/2026-05-30-top-level-design-v2.html
depends_on: docs/superpowers/specs/2026-05-30-source-ready-design.md(dry-run)
---

# ①源到位 · Phase-2(apply)设计 spec

## 0. 与 dry-run 的本质区别

dry-run 只读,产出"建议"。**Phase-2 会改 vault 真实语料**(移文件、按 SCHEMA §C 重算 id)。higher-stakes,故:
- 全程**可逆**:删=git mv 到 `_archive`/`_duplicates`(不真删);id 改走 §C 白名单(旧 id 留 aliases,记 `*_fixed_*` 审计字段)。
- apply 前给 **vault 打 git tag checkpoint**(`pre-source-apply-<date>`),随时回退。
- **整文件重生,零补丁**(charter 纪律):派生层不在本阶段动(③ 整体重建);本阶段只动 raw。

## 1. 范围

应用 dry-run 查出的处置;**分两阶段**(2a 先行、低风险,验证 apply 机器;2b 大头)。

### 2a · 确定性清理(先做,快、稳)
- **archive 2 篇真噪声**:`#7 P_2026_OTHERD5E7_03169880`(南京日报导航壳)、`#19 P_2025_HA_4aa32072`(信阳特写_市县)→ git mv 到 `0_raw/_archive/policies/source_audit_<date>/`
- **去重 25 篇**:dedup 12 组,每组留 date 最早,其余 git mv 到 `0_raw/_duplicates/` + 写 `_duplicate_of` 等字段(SCHEMA §2)
- 判断型(dedup 组)**先抽样校 ≥95%** 再 apply;archive 2 篇逐条人工确认(量小)

### 2b · GO/SC id 重算(大头,me-as-LLM 逐批)
- **分类+解析 ~190 篇**(177 GO + 11 SC + 1 canonical):我(agent 当 LLM)逐批读正文,判 `policy / market_intel / noise` + 解析真实 `issuer` + `region`
- **只对"policy"的**按 §C 重算 id(issuer_short + region + 旧 id 入 aliases + 审计字段);
- **market_intel 的不动**(按推后约定,记录到 manifest,等第三源建设);
- **noise 的** archive。

## 2. me-as-LLM 逐批分类机制

- 批大小 ~40 篇/批(约 5 批)。每批:脚本 dump `pid/title/url/issuer/issuer_canonical/body_head` → 我读 → 产出 `{pid, class, true_issuer, true_region, confidence, evidence}` → 写 `state/source_ready/go_sc_review/batch_N.jsonl`
- **抽样校 ≥95%**:对我判的结果抽 30-50 条复核(可换一批 prompt 自检 / 人工抽),达标才进 apply
- 维护期换成 API LLM 注入(同 DI 口子)

## 3. apply 动作(确定性脚本,读 review 结果 → 改 raw)

| 处置 | 动作 | 可逆 |
|---|---|---|
| archive(noise) | git mv → `_archive/policies/source_audit_<date>/` + log | ✓ |
| dedup | git mv 非最早者 → `_duplicates/` + 写 dedup 字段 | ✓ |
| id 重算(policy) | 就地改 `id`/`issuer`/`issuer_canonical`/`region`,**旧 id 留 aliases**,记 `id_fixed_at/_method/_from` 等(§C)| 审计留痕 |
| market_intel | **不动**,写入 `state/source_ready/market_intel_manifest.jsonl`(留待第三源)| — |

- **不 remap 派生层**(③ 整体重建)。
- 脚本:`scripts/l1_audit/apply.py`(新);TDD:在小 fixture vault 上测 archive/dedup/id 重算 + 幂等(重跑 no-op)+ 可逆(_archive 可恢复)。

## 4. checkpoint + 提交

- apply 前:`git -C <vault> tag pre-source-apply-<date>`
- 2a 一个 commit,2b 一个 commit(vault 仓);写 `state/source_ready/apply_log.jsonl`
- 完成后更新 `state/STATUS.md`:政策数变化、各处置数、抽样精度

## 5. 不做(YAGNI / 推后)

- ❌ market_intel 第三源建设(docs/BACKLOG.md B1,推后)
- ❌ 关系/business/结晶 重建(③)
- ❌ 重抓 raw
- ❌ remap 派生层(③ 整体重建时一次性来)

## 6. 验收门(done-gate)

- 2a:25 去重 + 2 archive 应用完,vault 政策数对账一致,_archive/_duplicates 可恢复验证过
- 2b:~190 篇分类抽样 ≥95%;policy 的 id 重算后 id-issuer 一致性复跑 → 高置信 mismatch 归零;market_intel manifest 落盘;noise archive
- 全程有 checkpoint tag,可一键回退
