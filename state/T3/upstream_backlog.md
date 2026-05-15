# T3 上游 Backlog · 抓取链路 + 派生层文本问题

_generated_at: 2026-05-12_
_driver: T3 P_1900 inventory + archive 过程中发现_

T3 修复了"id drift"这层症状,但揭示了上游若干根因。本文件登记 backlog 项,**不**作为 T3 范围内任务,留给 L1 抓取改造和后续 cleanup pass。

## 1. 抓取"footer-only"问题

2 篇 A 类 archive 政策(#1 / #17)body 只有 ~250 字,内容全是页脚导航(微博/公众号/ICP 备案/版权),trafilatura 没抽到正文主体。

- `https://sthjj.beijing.gov.cn/bjhrb/index/xxgk69/zfxxgk43/fdzdgknr2/zcfb/hbjfw/436340838/index.html`
- `https://sthjj.beijing.gov.cn/bjhrb/index/xxgk69/zfxxgk43/fdzdgknr2/zcfb/shbjgfxwj/index.html`

**域名特征**:`sthjj.beijing.gov.cn`(北京市生态环境局)。
**建议**:L1 抓取该域名走 firecrawl 兜底(参考 LESSONS B3 兜底链路设计)。

## 2. SEO 攻击页混入

1 篇 A 类 archive 政策(#25)是被 SEO 攻击的搜索结果页,URL 含推广关键词:

- `https://fzggw.ah.gov.cn/site/search/49631471?... telegram∶AK6793 ... USDT 充值 ...`

正文是同样的垃圾关键词重复。

**建议**:L1 入库前在 URL / title / body 前 200 字符里检测以下关键词列表,命中即跳过入库:
`telegram`, `∶AK`, `usdt`, `usdt`(全角), `免备案虚拟主`, `阿里云退款`, `华为云退款`, `打开∶`

## 3. relations evidence/reason 文本中的旧 id 残留

T3 Phase 3 完成后,relations 7 类 jsonl 中:
- 结构化字段 `from`/`to`:**100% remap 完成**
- 非结构化字段 `evidence`/`reason`:**19 行残留 P_1900_* 字符串**(都是当时 LLM 判定时生成的内容)

例:`{"from": "P_2023_GO_ab7afa77", "to": "P_2023_GO_1b2358a4", ..., "reason": "...maps to vault pid P_1900_GO_1b2358a4..."}`

**为什么不处理**:按 LESSONS A3,LLM 派生不被 mechanically 修改;aliases 保留旧 id,链接兜底解析。

**例外情况**:下一次 L2 relations 重跑时(rebuild_l2_rel_judge),LLM 会用当下 vault 状态重新写 reason,旧 id 字符串自然消失。这是"等下一次重跑自然修复"的 backlog 项,不专门处理。

## 4. business_view 派生不完整

T3 Phase 3 发现:84 篇 B/C 类政策中,只有 72 篇有对应的 business_view yaml(剩 12 篇没派生过)。

**原因推测**:业务视图生成不是全量跑,而是按筛选条件(可能筛掉了被 classifier 标 `news_or_press` / `index_page` 的政策)。

**建议**:T3 之后可以重新触发 business_view 生成,看是否需要补这 12 篇。不在 T3 范围内。

## 5. P_1900_SX_caf8e7eb(D 类山西)单独处理

1 篇 D 类政策 date 字段真空,正文里有"发布时间:2025/05/26"但 URL path 没带日期。

**建议**:T3 + T2 完成后,做一个专门的"D 类残留处理"oneshot:
1. 用更宽松的正文 date 抽取(扫"发布时间[:|：]\s*(\d{4})[年/-]?(\d{1,2})[月/-]?(\d{1,2})日?"等多种模式)
2. 若抽到 → 走 Phase 2b 风格的 patch
3. 若失败 → 人工标 `date_unknown: true` 留人工补
