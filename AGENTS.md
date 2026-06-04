# AGENTS.md

Codex 在本仓工作时必须同时遵守本文件、`CLAUDE.md`、`SCHEMA.md`、`LESSONS.md` 和 `docs/BACKLOG.md`。若上下文落在别的目录,先确认是否应切回本工程仓。

## 核心原则

1. **规则优先,不打补丁**
   - 个案 PID 可以用于诊断、报告、回归样本,不能进入业务代码白名单、per-PID 分支或人工绕过表。
   - 发现误判时,先归纳为全局规则、registry、prompt 边界、程序门或人工待办池。

2. **TDD 和验证**
   - 新功能、bugfix、行为变化先写失败测试,再做最小实现。
   - 完成前跑对应测试;不能验证时明确说明。

3. **dry-run before apply**
   - 任何写 vault 的动作必须先 dry-run 产出变更集和 HTML 报告。
   - apply 只写 dry-run 已接受的集合;仍入队的项目不得自动写。

4. **raw 不可变边界**
   - `0_raw/` 默认只读。例外只按 `SCHEMA.md §C` 的确定性白名单和 provenance 规则执行。
   - LLM 判断只能落派生层或队列,不能直接改 raw。

5. **人工确认池**
   - 全局规则先判断文件/业务应放在哪一类或哪几类;若规则无法确定,进入 review queue / backlog。
   - 人工读取待办池证据后,给出"放在哪/放入哪些/保持待办"的裁决,并记录理由与来源。
   - 人工裁决是数据层结论,必须回到正常流水线执行;不要写成源码 PID 特例,也不要绕过 dry-run/apply。
   - 若多条人工裁决暴露同一模式,再沉淀为全局规则、registry、prompt 边界或程序门。

6. **展示材料用 HTML**
   - 给人读的报告、评估、对比、验收门做成自包含 HTML。
   - 原始证据和机器数据保留 JSON/JSONL/YAML 等原格式。

7. **模型成本纪律**
   - Qwen 只用于有边界的 judge / sentinel / 小样本交叉检查。
   - 大批量生成默认使用既定低成本 generator;不要无界跑昂贵模型。

8. **工作闭环汇报**
   - 每个阶段性任务完成后,必须说明:当前在哪个大进程里、本步完成了什么、原则/门禁是否仍生效、建议用户做的下一步是什么。
   - 若下一步存在业务分叉,必须给出推荐路径和原因;不要只说"等待指示"。
   - 若前一步只是 preview、机制说明或临时上下文,必须明确它不能被误认为 apply、正式产物或下游已就绪。

## ②-B 特别红线

- `scripts/l2_themescore/` 源码不得出现真实政策 PID 字面量。运行:

```bash
python3 -m scripts.audit.principle_guard scripts/l2_themescore
```

- `review_queue/queue.jsonl` 是待裁决池:人工可给出归类/多归类/保持待办结论,但不能把 queue 当成绕过流水线的手工 apply 清单。
- `preview-accepted` / `apply-accepted` 只消费 accepted drafts,不能消费 queue。
- 11 条 queue 样本只能作为"小范围验证全局规则是否修好"的样本,不能按单篇写特例;后续修复必须落到 judge evidence window、theme id 归一化、zero-theme gate、JSON 结构、标准/目录弱提及边界等全局机制。
