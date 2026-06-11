# Codex 交接：WP-3a ③信号线夜间链（本地代码侧）

**背景**：信号线组件已齐：`scripts/commentary_signals/run.py`（dry-run，读 `0_raw/commentaries` + `_meta/themes_registry.yaml`）、`scripts/market_intel_signals/run.py`（dry-run，读 manifest，零 LLM）、`scripts/derived_signals/run.py`（preview→apply，review_queue 闸 + `_target_in_extracted` 路径闸，有测试）、`run_sync` 已消费 `1_extracted/commentary_signals.jsonl`。本包=把它们接成夜间 cron 链（文档）+ 两处小代码改动。**不新建编排器**，沿用 cron 行内 `&&` 链 + produce_and_push 白名单 + flock 模式。

**纪律（红线，违者中止）**：仓库内既有未跟踪文件一律不碰不提交；TDD 红绿分 commit（先 test commit 红，后实现 commit 绿）；不合 main、不 push，分支留给 Claude 审计；凭据值不打印不进 git；不碰 vault。

**分支**：`wp3/signals-nightly`（从 main `ecafdc7` 起）。

## 改动 1 · market_intel_signals 的 manifest 路径参数化（如已可参数化则跳过并说明）

检查 `scripts/market_intel_signals/run.py`：manifest 路径若硬编码 `state/source_ready/market_intel_manifest.jsonl`（仓库相对路径），加 `--manifest` CLI 参数（默认值保持现状，向后兼容）。服务器上 manifest 将放 `/state/source_ready/market_intel_manifest.jsonl`。带测试（红绿分 commit）。

## 改动 2 · 哨兵判活口径改 token 直检

今晨实战 bug：判活用 `qr_relay/feed_health.py::feed_token_status`（feed HTTP 200）误判"已恢复"——feed 是缓存，token 已死仍 200。修复：QR relay 哨兵判活调用点改用 `token_health.py::check_token`（读 wewe-rss sqlite `accounts.status`，`qr_relay/detector.py::token_needs_relay` 已有封装可用）。`feed_health` 可保留作诊断输出，但**判活决策必须以 token 直检为准**。找到实际调用点（哨兵 cron 入口链路）后改，带测试（红绿分 commit）。

## 改动 3 · runbook 加 03:00 夜间信号链 cron 行（仅文档）

`docs/runbooks/s2-vps-cron.md` §1 仿照 02:00 关系增量行新增 03:00 行，结构：

```
0 3 * * * ( flock -w 7200 9 || { notify "[S2] producer 锁等待超时,信号链跳过"; exit 1; };
  load notify.env; cd /root/policy-pipeline-src
  && docker compose run --rm policy-producer python -m scripts.commentary_signals.run dry-run --vault /vault --state /state/commentary_signals/nightly
  && docker compose run --rm policy-producer python -m scripts.market_intel_signals.run dry-run --manifest /state/source_ready/market_intel_manifest.jsonl --state /state/market_intel_signals/nightly <按实际 CLI 签名写>
  && docker compose run --rm policy-producer python -m scripts.derived_signals.run preview <commentary-state/market-state/out 按实际签名> --out /state/derived_signals/nightly
  && docker compose run --rm policy-producer python -m scripts.derived_signals.run apply <preview 目录> --vault /vault
  && /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault --whitelist "1_extracted/commentary_signals.jsonl,1_extracted/market_intel_signals.jsonl" --message "l2(signals): nightly derived signals"
  || notify "[S2] 03:00 信号链失败,查 signals.log"
) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/signals.log 2>&1
```

各子命令 flag 以代码/测试为准逐一核对后写成可直接照抄的真实单行（不要伪代码）。同时在 runbook 注明：state 三个 nightly 目录每晚覆盖重建属预期。

## 验证（本地）

`python3 -m pytest` 全绿（基线 586 ± 新增）；逐 commit 红绿可见；diff 范围仅限：market_intel_signals（如需）、哨兵判活调用点、对应测试、runbook。

## 回报

stdout 回报：分支名、commit 列表（红绿配对）、pytest 数字、改动 1 是否需要（或为何跳过）、哨兵调用点定位（文件:行）、cron 行全文。无需 report 文件。
