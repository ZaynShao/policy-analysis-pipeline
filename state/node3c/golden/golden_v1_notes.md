# ③-C golden_v1 冻结说明 (2026-06-06)

## 规模
- 总 45 行 = 真实 35 + 埋错 10
- gold_decision 分布: {'accept': 10, 'reject': 35}
- 真实对: accept 10 / reject 25
- 出处: {'high_consensus': 28, 'user_adjudicated': 7, 'planted': 10}

## ⚠ 诚实披露
1. **opus 全员 StructuredOutput 失败**,本轮 n_labelers=2(sonnet+haiku)。
   high = 两票一致、low = 两票分裂,**无 mid(2:1)档**。换强模型重跑可整体修正(整文件重生)。
2. **规则过度生成**:28 个 high 里 22 个被两模型一致 reject(extends 锚词太松、
   iterates 不分文件性质、aligns 未排除实为 derives 的)。golden 的 25/45 reject 由此而来——
   这是**有难度的测试集**(judge 须否掉规则误报+埋错、留住真 accept),不是 golden 的 bug。
   规则精度是否回头收紧 → 待校准看 judge 能否兜住再定(记 backlog)。

## 校准读法
- `planted_recall ≥ 0.9` = spec §13 达标线(只管 10 个埋错)。
- `agreement`(verdict==gold_decision 全量比对)= 更关键,衡量是否过度接受 25 个 reject。
  见谁都 accept 的 judge: real_accept_kept≈1 但 agreement≈10/35≈0.29,一眼穿帮。
