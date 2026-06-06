# ③-C judge 校准决策 (2026-06-06)

judge = **deepseek-v4-flash** @ api.deepseek.com,golden = `golden_v1.jsonl`(45=真35+埋10)。

## 两轮结果
| 指标 | cycle0(原prompt) | cycle1(收紧·**已锁定上岗**) |
|---|---|---|
| planted_recall(bar≥0.9) | 1.0 ✓ | **1.0 ✓** |
| agreement(verdict==gold) | 0.486 | **0.829** |
| 入库精度(accepted里对的) | 64% (7/11) | **100% (6/6)** |
| 真关系召回 | 70% | 60% |
| 过度接受(污染) | 4 | **0** |
| 人工池占比 | 40% | **6%** |

## cycle1 改了什么(`judge.py` SEMANTIC_RELATION_JUDGE_SYSTEM)
- **iterates** 收紧:版本升级/修订同一文件框架才算;各自响应不同上位触发的独立事件(如每次调价对应不同上位通知)、性质不同文件(规划↔办法、征集↔申报)→ reject。修掉油价误判。
- **aligns_with** 收紧:同主题**且同政策工具/环节**才 accept;同领域但工具不同(定价↔监管、规划↔运营、项目申报↔价格管理)→ reject。修掉 3 个过度接受。
- **降对冲**:从"宁可进人工"→"先尽量判 accept/reject,仅证据不足判断方向/工具一致性时才 manual"。人工池 40%→6%。

## ⚠ 诚实披露:锁 cycle1 的已知代价
- **保守 aligns**:收紧"工具一致"的同一条规则,也自信否掉了 **3 个真 accept**——含用户亲手裁过的 **#5 安徽→辽宁**、**#7 广州→海南**(均 confident reject conf 0.90,**不进人工池=人审捞不回**)+ #08 安徽2021→北京2019(derives)。
- **为何不追 cycle2**:#7(广州管理 vs 海南补贴)与 #32(海南规划 vs 广州管理,gold=reject)结构近对称,280 字窗口的便宜判官无法稳定分开;放松必让 #32/#34 污染回归。用户拍:锁 cycle1。
- **兜底**:整文件重生哲学——将来换强模型重跑可整体恢复这些边界召回;Lever B(④消费层并集门)不重度依赖 aligns。
- aligns gold-accept 仅 n=3(召回数字噪声大),勿过度解读"33% aligns 召回"。

## 生产语义提醒
partition_by_decision:只有 `accept` 进 accepted;`reject`+`manual_review` 进人工池。故 cycle1 在全量 3075 上:accepted 是高精度子集(judge confident accept),其余进人工池/丢弃。Task10 只 preview,不 apply、不进 ④。
