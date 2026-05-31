---
title: ②-A 确定性身份固化 · 设计 spec
node: ②归属层 / 子项 A(确定性身份固化)
status: APPROVED(设计于 2026-05-31 brainstorm 获批,待转 writing-plans)
date: 2026-05-31
authority: 上位纲领 docs/2026-05-30-top-level-design-v2.html §1/§2/§8 · 数据契约 vault SCHEMA.md §C(v1.1)
---

# ②-A 确定性身份固化 · 设计

## 0. 一句话

建一条**常驻确定性身份 resolver**:一个 dumb 确定性引擎 + 几张查表(判断放数据、不放代码),全语料幂等地把破损的身份字段(`id / issuer / issuer_canonical / region / date`)修对。**域名是锚**,标题只在被域名背书时采信;信号干净且与 ledger 一致才**写 raw**,否则**入待裁决队列**(不写)。

## 1. 目标 & 非目标

### 目标
- 把 `0_raw/policies/` 里破损的身份字段修到确定性正确,使 issuer/region/date/id 可信——这是 ②归属 挂 theme/region、④ API 查询轴(时间×地点×主题)的地基。
- 产出可复用的源资产(域名→机构/区域查表),**未来 L1 入库走同一套**,不是一次性清洗。

### 非目标(明确不做)
- ❌ theme 挂载、重要性打分 → ②-B(派生视图)。
- ❌ B3(4 篇 commentary 误入 policies 的跨语料搬家)→ 单独小 pass。
- ❌ B5(词表 4 处 theme 不自洽)→ ②-B theme 匹配时定。
- ❌ 用 LLM 自由生成值写 raw(§C 红线)。
- ❌ 派生层引用旧 id 的重指(§C 要求独立 oneshot、不与 raw 改动同 commit;本阶段派生层多为化石,只登记,留 ②-B/③ 重建时做)。

### 含
- ✅ B4(`P_2027_GO_572b0ea8` date 损坏)——被 date 规则自动收掉,不单列。

## 2. 背景 & 约束

### 2.1 破损现状(实测,vault 935 篇)
| 破损类型 | 数量 |
|---|---|
| id 前缀 GO/SC 万能桶 | 149(134 GO + 15 SC) |
| issuer 字段是垃圾域名串(`政府门户.www.xxx.gov.cn`) | 76 |
| region.name = 未知/空 | 51 |
| id 不符 `P_YYYY_PREFIX_` 格式 | 30 |
| **破损集并集(GO/SC ∪ 垃圾issuer ∪ region未知 ∪ 畸形id)** | **179** |

破损集 179 篇里:**163(91%)有干净 `*.gov.cn` 域名 → 域名可直接解析**;16 篇非 gov 域名(全是 `in-en.com` 行业镜像,八成是 market_intel/误入)→ 落残渣;涉及 **96 个不同 gov 域名**。

破损根因:入库时 issuer 没抽到、退化成域名串;region 默认 `{level:国家, code:'000000', name:未知}`。**政策正文没问题**(不是抓错)→ 属 §C(从既有正确 metadata 重新算身份),非 §D(重抓)。

### 2.2 §C 合约(vault SCHEMA.md §C v1.1)
身份字段 `id / aliases / date / region / issuer / issuer_canonical` **允许就地改 raw,仅当新值由确定性规则从已有 metadata 算出(非 LLM 自由生成)**。每次重算必须在 `provenance` 记审计字段:`<field>_fixed_at` / `<field>_fixed_method`(枚举)/ `<field>_fixed_from`(原值)/ `<field>_fix_confidence`(可选)。method 枚举含 `domain_lookup` / `title_extract` / `body_chinese_date` / `id_recompute_from_metadata` / `combined` 等。id 重算后 aliases 必须同时含旧+新 id;文件名不变。

### 2.3 上位纪律
- 纲领 §1:源 vs 视图。date/region/issuer/文号 = **源**(高精度确定性事实)。固化它们 = §8 第 2 步"固化源"。
- 风险姿态(用户拍板):**保守·分级写**——干净且与 ledger 一致才写 raw,冲突/低信心/矛盾→不写、入队列。宁可少改,绝不写错值进 immutable raw。
- **滑坡自审(每步收尾必跑)**:① 常驻规则还是钉快照?② 代码有无针对具体 pid 的硬编码分支?③ 动的是源还是视图(动 raw 须 §C 授权)?④ 判断有没有从"源/规则"漏进"视图/产物"?任一不过 → 停,退回重做。

## 3. 架构:判断在数据,代码是 dumb applier

### 3.1 数据层(源资产 · 判断沉淀在这)
- **`channel_registry.yaml`**(域名 → 机构/区域):从 `00 背景资料/渠道目录.md` 播种,扩到覆盖 96+ 域名。每条:
  ```yaml
  - domain: www.jinan.gov.cn
    issuer_short: SD          # 省级码(地方按省级:见 id_short 方案)
    issuer_canonical: 济南市人民政府   # 渠道级机关名(粗)
    region: { level: 市, code: '370100', name: 济南市 }
  ```
- **行政区划码表**(GB/T 2260,省+市 → code):给 region.code。查不到的市 → 省级码 + 标记入队列。
- **id_short 方案**(① 已定,沿用):国务院=`GWY`(GO 留国办);地方 id_short = **省级码**(广州/广州某区/广东省→`GD`;杭州→`ZJ`;直辖市码=市码 BJ/SH/TJ/CQ);四川=`SC`;department 不进 id(进 issuer 字段)。

> 不规则的域名 → 进表(数据,可审),不进代码 → **没给补丁留位置**(滑坡红线)。

### 3.2 代码层(pipeline · 纯函数 + applier)
- **`resolver.py`**:纯函数 `resolve_identity(raw_fm) -> ResolvedIdentity | Conflict`。读 `provenance.url` / `official_number` / `title` / body,查表,产出 `{id, issuer, issuer_canonical, region, date}` + 每字段 method + confidence,或标记 conflict/unknown。**零 pid 分支。**
- **`apply_identity.py`**:对 resolve 结果,§C 合规就地写 raw frontmatter。**复用 T3 oneshot 的最小-diff frontmatter 改写 + id 碰撞检测**(`scripts/_oneshot/t3_phase2a_recompute_id_c.py` 的 `patch_frontmatter` / `scan_existing_ids` 思路;**注意**:多字段 + 嵌套 region 比 T3 单字段复杂,实现时评估"最小-diff regex"还是"yaml round-trip",以可测 + diff 干净为准)。审计字段写 **嵌套 `provenance`**(修正 ① 那个写顶层的 remint_id primitive)。
- **review_queue 产出** + **验收门 check** + **dry-run/apply/verify CLI**(沿用 ① 的 dry-run→apply→tag 模式)。

## 4. resolver 逻辑(确定性 · 每字段)

| 字段 | 来源(确定性) | method |
|---|---|---|
| `region.{level,code,name}` | 域名 → channel_registry → adcode 表 | `domain_lookup` |
| `issuer_short`(用于 id) | 域名 → channel_registry | `domain_lookup` |
| `issuer / issuer_canonical` | **标题 H1 抽取,须与域名渠道一致才采信**;不一致→队列 | `title_extract`(+ `domain_lookup` 背书) |
| `date` | 正文**落款**中文日期(issuer 签名块/文末);干净抽到即写(覆盖错误现值,如 B4 的 2027→2023);抽不到/多歧义→保留现值,现值也明显坏(如 2027/1900)→队列 | `body_chinese_date` |
| `id` | `P_<year(date)>_<issuer_short>_<原hash>`;碰撞加 `_a/_b` | `id_recompute_from_metadata` |
| `aliases` | 旧 id 必留 + 新 id | —(随 id) |

**issuer 决策(用户选项 A,改了渠道目录一条规则)**:渠道目录原规则"不从标题取机构"细化为"**标题须经域名背书**"——标题抽出的机关名与域名渠道一致(济南文件:标题"济南市人民政府办公厅" × 域名 jinan.gov.cn→济南 ✓)才写精确名;不一致(转载/联合发文/媒体/个人/企业)→ 入队列。

## 5. 冲突 → 待裁决队列(保守姿态的物理形态)

- **冲突定义**:标题机关与域名渠道不符(转载/联合发文/媒体/个人/企业)· resolver 结果与 ledger 矛盾 · date 落款抽不到且现值明显坏 · 非 gov 域名(无法域名解析)。
- **注**:`official_number`(文号)**不作为 region/issuer 的写入来源**——文号常反映被引用的上位文(如济南件引"鲁政办字"省级文号),用它定 region 会把"引用"错当"本体"。**region 唯一来源是域名。**
- **处置**:该字段不写,整条入队列,记下各信号的值 + 证据 + 哪条规则触发。
- **队列落点**:`state/source_ready/2a_review_queue.jsonl`(进程产物,gitignore);与 vault 已有 `_meta/issuer_review_queue.yaml` 对齐口径。
- **下游消费**:本阶段只产出 + 登记,**不靠 LLM 写回 raw**(守 §C)。深度校准(逐条裁决/issuer 全名精校)→ **②-B issuer 规范化**(那边已有 entity-registry + 该队列);进 BACKLOG + 记忆,到 ②-B 触发点主动提醒。

## 6. ledger 作为 oracle(不是真值)

`state/source_ready/attribution_ledger_2b.jsonl`(115 条 LLM 判定的 true_issuer/true_region/suggested_issuer_short)**只当验收交叉校验 oracle**:resolver 自己从域名/标题算值,拿 ledger 比对——一致=高信心写;矛盾=进队列。ledger 用完即弃,**不进 pipeline 依赖**(否则就退化成"吃台账的一次性补丁")。

## 7. 验收门(先定后建 · 纲领 §4)

1. **ledger 一致率 ≥ 95%**:resolver 对 115 条与 ledger 一致(双方都给值的子集;冲突算"未判"不算"错")。
2. **幂等**:apply 后重跑 resolver = 0 改。
3. **SCHEMA validator** 全过(`scripts/audit/validate_schema.py`)。
4. **代码审查**:resolver 零 pid 硬编码分支(滑坡红线)。
5. **可逆**:全 git rename + vault checkpoint tag,可整体 `git reset --hard` 回退。
6. **可解释**:写入项 100% 有 method + from 审计。

## 8. 数据流 & CLI

```
935 raw + channel_registry + adcode + ledger(oracle)
  → resolver 逐篇算 identity
  → 分流:  干净 & 与ledger一致 → apply 集
            冲突/低信心/矛盾/未知 → review_queue(不写 raw)
  → dry-run: 产 proposed_changes_2a.jsonl + 2a_review_queue.jsonl + HTML 验收报告(用户过目)
  → apply:   §C 就地写 raw + git rename + apply_log_2a.jsonl
  → verify:  幂等=0改 + validator + ledger 一致率
  → vault checkpoint tag pre-2a-2026-xx
```

## 9. 测试(TDD)

- **resolver 纯函数单测**:national 域名 / 省级 / 市级 / 直辖市 / joint issuer / 域名vs文号冲突 / date 三值冲突 / 标题与域名不符(转载) / 非 gov 域名→unknown / 已正确→no-op。
- **apply 测**:临时 vault fixture,断言 frontmatter(id/issuer/region/date)+ aliases(旧+新)+ provenance 嵌套审计字段 + 文件名不变 + git rename。
- **验收门 check 测**:一致率计算、幂等检测、碰撞 `_a` 后缀。

## 10. 默认值(brainstorm 已认可)

| 项 | 默认 |
|---|---|
| channel_registry 落点 | 新建 vault `_meta/channel_registry.yaml`(机器源);`渠道目录.md` 保留为人读视图 |
| region.code 来源 | 标准 GB/T 2260 码表;查不到的市 → 省级码 + 标记入队列 |
| 队列落点 | `state/source_ready/2a_review_queue.jsonl`(gitignore) |

## 11. 滑坡自审记录(本设计自查)

- ① 常驻规则? ✅ channel_registry/adcode 表 + dumb applier,全语料幂等,未来入库复用;ledger 仅 oracle。
- ② pid 硬编码? ✅ 无——不规则域名进 YAML 表(数据,可审),非代码分支。
- ③ 源 vs 视图? ✅ channel_registry = 新 canonical 源资产;写 raw = §C 授权确定性身份重算;队列 = 派生层(非 raw)。
- ④ 漏进视图? ✅ 队列显式在派生层;ledger 只当 oracle;LLM 判定不写 raw。
- **四条全过。**

## 12. 后续触发(别忘机制)

- **issuer 队列校准** → ②-B issuer 规范化(entity-registry + 本队列);登记 BACKLOG + 记忆,到 ②-B 主动提醒。
- **派生层旧 id 重指** → ②-B/③ 重建时做(§C:独立 oneshot,不与本次 raw 改动同 commit)。
- **B3 / B5** → 各自单独节点(见 BACKLOG)。
