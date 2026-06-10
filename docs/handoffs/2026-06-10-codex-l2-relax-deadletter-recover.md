# Codex 交接:L2 放宽同模型 + drain 死信修复 + 恢复 32 pid + 重跑

**背景**:Step 3 L2 首跑全失败——`run_2b.py` 硬断言 `gen_model != judge_model` 撞了"gen+judge 都 deepseek-v4-flash"。且 `drain_queue` 无条件 `mark_complete`,32 个失败 pid 被抽出队列(现 l2_queue=0,ledger=0 干净,raw 安全在 vault `feefc9b`)。

**用户决策**:① 放宽断言(单模型 deepseek,允许同模型,降为告警);② 修 drain 静默丢弃 wart(失败进死信、不丢);③ 恢复 32 pid 重跑。

**服务器**:`ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`,repo `/root/policy-pipeline-src`,vault `/root/policy-vault`,state `/root/policy-pipeline-state`(容器内 `/state`)。

**纪律(红线)**:凭据不打印/不进 git;vault 写只经 produce_and_push;手跑生产命令持 flock;**两处代码改走 TDD,diff 贴回等 Claude 审过再合**;任一步报错停下原样贴输出。

---

## Part 1 · 两处代码改(TDD,一个分支 `fix/l2-relax-deadletter`)

### 改 A — `scripts/l2_themescore/run_2b.py`:断言降为告警

import 行(line 1)加 `sys`:
```python
import argparse, html, json, sys
```
新增纯函数(放 `make_client` 附近):
```python
def warn_if_same_model(gen_model: str, judge_model: str) -> None:
    """gen==judge 时告警(judge 退化为自评),不再硬阻断——单模型部署的有意放宽。"""
    if gen_model == judge_model:
        print(f"[warn] gen 与 judge 同模型({gen_model}):judge 独立性退化为自评，质量打折",
              file=sys.stderr)
```
line 362 的 assert 替换为调用:
```python
        warn_if_same_model(args.gen_model, args.judge_model)
```
(删除 `assert args.gen_model != args.judge_model, "judge 模型必须 ≠ generator 模型"`。)

**测试**(`tests/l2_themescore/test_run_2b*.py` 追加;若无则建,带包内 `__init__.py`):
```python
def test_warn_if_same_model_warns_not_raises(capsys):
    from scripts.l2_themescore.run_2b import warn_if_same_model
    warn_if_same_model("deepseek-v4-flash", "deepseek-v4-flash")   # 不抛
    assert "退化" in capsys.readouterr().err

def test_warn_if_same_model_silent_when_different(capsys):
    from scripts.l2_themescore.run_2b import warn_if_same_model
    warn_if_same_model("a", "b")
    assert capsys.readouterr().err == ""
```

### 改 B — `scripts/service/orchestrate.py`:drain 失败进死信不丢

import 区加:
```python
from datetime import datetime, timezone
```
新增 helper(放 `drain_queue` 之前):
```python
def _record_failure(queue_path: Path, pid: str, error: str | None) -> None:
    """失败 pid 落死信(队列同目录 l2_failures.jsonl),append-only,可人工/sweep 重排。"""
    dead = Path(queue_path).parent / "l2_failures.jsonl"
    rec = {"pid": pid, "error": (error or "")[:300],
           "ts": datetime.now(timezone.utc).isoformat()}
    with open(dead, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
```
`drain_queue` 改两处。raw_missing 分支(原 `results.append(StageResult(... raw_missing ...))` 下一行)插入死信记录:
```python
        except Exception as e:
            results.append(StageResult(item.pid, False, f"raw_missing: {e}"))
            _record_failure(queue_path, item.pid, f"raw_missing: {e}")
            l2_queue.mark_complete(queue_path, item.pid)
            processed_any = True
            continue
```
主处理分支(原 `mark_complete`+`save_ledger` 无条件那段)改成按 ok 分流:
```python
        res = process_pid(item.pid, raw_text, version, ledger,
                          run_attribution, run_crystallize)
        results.append(res)
        if res.ok:
            l2_queue.mark_complete(queue_path, item.pid)
            save_ledger(ledger_path, ledger)
        else:
            _record_failure(queue_path, item.pid, res.error)   # 失败不静默丢
            l2_queue.mark_complete(queue_path, item.pid)        # 出队避免无限重试同一 pid
        processed_any = True
```

**测试**(`tests/service/test_orchestrate*.py` 复用现有 drain 夹具,追加):
```python
def test_drain_failed_pid_to_dead_letter_and_dequeued(tmp_path):
    """run_attribution 抛错的 pid → ① 进 l2_failures.jsonl ② 出主队 ③ 不进 ledger。"""
    # 用现有夹具构 queue(含 1 个 pid)+ 注入 run_attribution=抛异常;
    # 断言:drain 后 next_item(queue)==None;(state_dir/l2_failures.jsonl) 含该 pid;ledger 无该 pid。
```
(按现有 test_orchestrate 的 queue/ledger 构造方式写;成功路径已有测试,确认仍绿。)

**跑**:相关测试先红后绿 → 全量 `python3 -m pytest -q`(应 565+ 全绿)→ 提交分支 push → **diff 贴回等 Claude 审过再合 main**。

---

## Part 2 · 合并 + 部署(镜像重建,代码在容器内跑)
**重建的是 `policy-pipeline` 服务**(它有 `build: .`);`policy-producer` 只引用同一 `image: policy-pipeline:latest`,对它 build = `No services to build` 的 no-op(2026-06-10 踩过:l2-relax 没更新镜像、队列被旧镜像二次抽空)。
```bash
cd /root/policy-pipeline-src && git fetch origin && git reset --hard origin/main
docker compose -f docker-compose.server.yml build policy-pipeline   # ← 是 policy-pipeline,不是 policy-producer!
docker run --rm policy-pipeline:latest python -c "import trafilatura, bs4; print('build ok')"
# 镜像验证闸(两处改必须都在镜像里,否则停,别往下跑——否则旧镜像又抽空队列):
docker run --rm policy-pipeline:latest sh -c "grep -c warn_if_same_model scripts/l2_themescore/run_2b.py; grep -c _record_failure scripts/service/orchestrate.py"
# ↑ 两行都应输出 ≥1;若 run_2b 仍含旧 assert 或 orchestrate 无 _record_failure → 镜像没更新,停下排查
```

## Part 3 · 恢复 32 pid 重排(host 取文件清单 → 容器读 id 入队)

**Step R1(host,NUL 分隔避免中文名/控制字符)**:
```bash
cd /root/policy-vault
git -c core.quotepath=false diff-tree --no-commit-id --name-only -r -z feefc9b \
  > /root/policy-pipeline-state/_recovery_files.z
```

**Step R2(容器:读清单→提 frontmatter `id:`→enqueue_batch,带数目安全闸)**:
```bash
cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer python -c "
from pathlib import Path
from datetime import datetime, timezone
from scripts.service.l2_queue import enqueue_batch
data = open('/state/_recovery_files.z', encoding='utf-8').read()
files = [f for f in data.split(chr(0)) if f.startswith('0_raw/policies/')]
pids = []
for f in files:
    for line in Path('/vault', f).read_text(encoding='utf-8').splitlines():
        if line.startswith('id:'):
            pids.append(line.split(':',1)[1].strip()); break
pids = sorted(set(pids))
assert 25 <= len(pids) <= 35, f'pid 数异常 {len(pids)}(预期 ~32),停止不入队'
enqueue_batch(Path('/state/l2_queue.jsonl'), pids, 'l2_recovery', 'normal',
              datetime.now(timezone.utc).isoformat())
print('re-enqueued', len(pids))
"
wc -l /root/policy-pipeline-state/l2_queue.jsonl     # 应 ~32
rm -f /root/policy-pipeline-state/_recovery_files.z
```
判据:打印 `re-enqueued ~32`、队列行数 ~32。数目异常(assert 触发)→ 停,报告,别硬塞。

## Part 4 · 重跑 L2 → push → 投影 → 解 cron(回到 w2w3 手册 Step 3)
```bash
( /usr/bin/flock -w 600 9; set -a; . /etc/policy-pipeline/notify.env; set +a; \
  cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.service.run_l2 --vault /vault --state-dir /state \
    --gen-model deepseek-v4-flash --gen-provider openai \
    --judge-model deepseek-v4-flash --judge-provider openai \
) 9>/var/lock/policy-pipeline-producer.lock
```
判据:`{processed, ok, failed, skipped}`,**这次应 failed=0 / ok=~32**;`[warn] gen 与 judge 同模型` 出现是预期(放宽生效)。若仍有 failed:看 `/root/policy-pipeline-state/l2_failures.jsonl`,贴错误(脱敏),停。

ok 后:**Step 3 push → Step 4 投影 → Step 5 解 cron**,全照 `docs/handoffs/2026-06-10-codex-s2-w2w3-night.md`(Step 3 的 produce_and_push 已带 `cd` 前缀;Step 5 sed 把 L2 cron 行改 deepseek/openai 再解注释)。

---

## 回报
逐 Part:改 A/B 的 diff + 测试结果(先红后绿 + 全量数字)、Part 3 的 re-enqueued 数与队列行数、Part 4 的 `{processed/ok/failed}` 与 l2_failures 是否为空、push/投影/crontab 终态。续写 `docs/handoffs/2026-06-10-codex-s2-w2w3-report.md`。
