# Codex 交接：存量 raw 的"发文日误标"回填(date/id 再解析)

**背景**:L1 `date` frontmatter 系统性把"生效/截止/执行起始日"写进了 `date`,而非"发文/印发/落款日",按月过滤会漏掉真实发文于该月的政策(2026-05 能源月刊 L-cov 查漏发现)。证据:
- `P_2026_ZJ_FGW_21`:落款 2026-05-28,却 `date='2026-07-01'`(误取"自2026年7月1日起执行");`official_number` 还误抓被废止旧件号 `浙发改价格〔2024〕21号`。
- `P_2027_NDRC_572b0ea8`:落款"二〇二三年九月"(中文数字),却 `date='2027-01-01'`、id 桶错成 2027。
- `P_2026_BJ_559a203d`:`date='2026-12-31'`(截止日)。

**抽取层机制已修并合并(不要重写)**:本次抽取逻辑已做成单一真相源并入仓、全绿(625 passed):
- `scripts/l1_collect/cn_dates.py`(新)— `pick_issuance_date(text)`(剔除生效/截止候选、识别中文数字落款、缺日补 01、落款取文末中性日期)、`is_effective_or_deadline_date(text, date)`、`cn_year_to_int` / `cn_md_to_int`。
- `scripts/l1_collect/metadata_extractor.py` — `extract_date` 正文回退改走 `pick_issuance_date`;`extract_official_number` 跳过废止/失效上下文里的旧件号。
- `scripts/l2_attribution/extractors.py::extract_luokuan_date` — 改为复用 `pick_issuance_date`(识别中文数字)。
- `scripts/l2_attribution/resolver.py` — date 块新增"保守修"分支:存量 date 貌似合理、但 `is_effective_or_deadline_date` 实锤它是生效/截止日、且落款是另一个发文日 → 改;否则不动(`test_valid_date_not_overwritten` 仍绿)。

**你的活**:写一个**存量回填 oneshot**,扫 `0_raw/policies/` 全量,**复用上面已合并的函数**(不要另写日期正则),对误标 date 做确定性再解析 + id 重算,带 dry-run/--apply,apply 经 `produce_and_push` 白名单。模型照搬 `scripts/_oneshot/t3_phase2b_recompute_id_b.py` 的 patch_frontmatter / aliases / §C 审计字段写法。

**用户已拍板的口径(保守自动修 + 其余入队)**:误伤好数据≈零优先于揪全;拿不准的进 review 队列+报告等人工,不自动写。

---

## 纪律(红线)

- **TDD 红绿分 commit**。
- 只许**新增** `scripts/_oneshot/date_issuance_backfill.py` + `tests/_oneshot/test_date_issuance_backfill.py`(或就近 tests 目录)。**不要改** `cn_dates.py` / `metadata_extractor.py` / `extractors.py` / `resolver.py`——它们是本次已合并产物,直接 import 复用。
- **raw immutable**:只允许就地改 §C 身份字段(`id`/`aliases`/`date` + `provenance.*_fixed_*`),不动 body、不动 issuer/region、**不动 `official_number`**(见下"official_number 只标记")。
- **不写生产 vault**:apply 路径必须经 `scripts/service/produce_and_push.run(vault, ["0_raw/policies/"], msg)`;凭据/真跑由操作者经手。dry-run 谁都能跑。
- 分支 `fix/date-issuance-backfill`(从 main 最新起);不合 main 不 push。

## 每篇决策逻辑(确定性,与 resolver 同口径)

```
url        = provenance.url
full_body  = frontmatter 之后的正文
tail       = full_body[-1200:]                       # 落款在文末
cur_date   = frontmatter.date
authoritative = extract_date(url, tail)              # URL 发布日优先,否则 tail 落款
broken     = cur_date 不是 YYYY-MM-DD 或年份不在 [1990, 本年] 或 P_1900 占位
mislabeled = is_effective_or_deadline_date(full_body, cur_date)   # 全文判生效/截止实锤

# 自动修(写 date):
if broken and authoritative:                         # 破损 → 补
    fix date = authoritative
elif mislabeled and authoritative and authoritative != cur_date:  # 实锤误标 → 改
    fix date = authoritative
# 入队不写(其余):
elif authoritative and authoritative != cur_date:    # 抽到的与存量不一致但非实锤 → review 队列
    queue
else:
    no-op                                            # 信任存量,或抽不到
```

- date 改且**年份变** → 重算 id:`P_<新year>_<原issuer_short>_<原hash/num 尾段>`;旧 id 入 `aliases`(保 Obsidian 反链);文件名不变。年份不变则只改 date,不改 id。
- §C 审计:`provenance.date_fixed_at/method/from`(method 用 `body_chinese_date` 或 URL 来源对应枚举)、id 改时加 `id_fixed_at/method(=id_recompute_from_metadata)/from`。
- **中文数字"只到月"落款**(如 二〇二三年九月 → `2023-09-01`,日是补的):年/月修复价值高(纠正 id 桶),但**日是造的**——这类单独成桶,`date_fix_confidence` 给低(如 0.7),报告里单列,提示人工扫一眼。

## official_number 只标记,不自动写

`official_number` **不在 SCHEMA §C 确定性重算白名单**(§C 只含 id/aliases/date/region/issuer)。因此本 pass 对它**只在报告里标记**:用已修好的 `extract_official_number(full_body)` 复算,若与存量不同(尤其存量是废止号)→ 列入"official_number 待复核",**不写 raw**。要自动改需先走 SCHEMA §C 修订流程(另起提案)。附带说明:id 尾号沿用旧 hash/num(同 t3),故误抓的文号尾号不会被本 pass 纠正,属上述同一待决项。

## 输出

- **dry-run 报告(HTML)**:总数 + 分桶(broken 补 / 生效误标 / 截止误标 / 中文月-only / ambiguous 入队 / official_number 待复核),每桶计数 + 前若干篇完整 frontmatter diff 预览;review 队列写 `state/date_backfill/queue.jsonl`。
- apply 日志写 `state/date_backfill/apply_log.jsonl`。

## 测试(红先行)

构造 tmp vault md(自带 frontmatter + body),覆盖:
- 生效误标(date=生效日 + 落款不同)→ 自动修到落款、id 年份不变不改 id。
- 截止误标(date=截止日)→ 修到落款。
- 跨年误标(date=2027 生效 + 中文落款 二〇二三年九月)→ date=2023-09-01、id 重算到 P_2023_*、旧 id 入 aliases、`date_fix_confidence` 低。
- broken/P_1900 占位 + 可抽落款 → 补。
- **合理 date 且非实锤**(抽到的落款不同但 cur_date 不在任何生效/截止句)→ **不动**(对齐 `test_valid_date_not_overwritten`,防误伤)。
- 抽不到权威日 → 不动 / 入队。
- official_number 存量是废止号、复算不同 → 进"待复核"、raw 的 official_number 不变。
- 幂等:apply 后再 dry-run → 0 改动。

## 验证

`python3 -m pytest tests/_oneshot/test_date_issuance_backfill.py -q` 全绿;`python3 -m pytest -q` 不回退(应 ≥625 passed)。然后**操作者**在真 vault 跑 dry-run(`--show-diff`)肉眼核三篇证据政策,确认后才 `--apply` + produce_and_push。

## 回报

stdout:分支、红绿 commit、pytest 数字、决策分桶计数(dry-run 在样例上的)、HTML 报告路径。无需单独 report 文件。跑完在 commit message 标 `[oneshot complete]`(7 天归档纪律)。
