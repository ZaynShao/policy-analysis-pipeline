# WP-3b 服务器部署监督报告

时间: 2026-06-11 16:30 CST

结论: **中止于 Step 1 manifest 初始化**。`origin/main` 的 `c638cef` checkout 中缺少交接要求的 `state/source_ready/market_intel_manifest.jsonl`, 因此未进入 Step 2 首跑、Step 3 投影、Step 4 cron、Step 5 哨兵实测。

## Step 0 部署

命令:

```bash
cd /root/policy-pipeline-src
git fetch --depth=1 origin main
git reset --hard origin/main
git rev-parse --short HEAD
docker run --rm policy-pipeline:latest python -c "import scripts.commentary_signals.run, scripts.market_intel_signals.run, scripts.derived_signals.run; print('IMAGE_OK')"
```

关键输出:

```text
HEAD is now at c638cef fix(signals): wire nightly signal health checks
c638cef
IMAGE_OK
```

结果: 通过。未重建镜像。

## Step 1 manifest 初始化

命令:

```bash
mkdir -p /root/policy-pipeline-state/source_ready
test -f /root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl && echo "已存在,跳过" || \
  cp /root/policy-pipeline-src/state/source_ready/market_intel_manifest.jsonl /root/policy-pipeline-state/source_ready/
wc -l /root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl
```

关键输出:

```text
cp: cannot stat '/root/policy-pipeline-src/state/source_ready/market_intel_manifest.jsonl': No such file or directory
```

只读诊断:

```bash
cd /root/policy-pipeline-src
git ls-tree -r --name-only HEAD | grep -E '(^|/)market_intel_manifest\.jsonl$|source_ready' || true
find state -maxdepth 4 -type f | sort | sed -n '1,120p'
```

关键结论:

```text
git ls-tree 未找到 market_intel_manifest.jsonl 或 source_ready 路径。
find state ... 输出中未出现 state/source_ready/market_intel_manifest.jsonl。
```

结果: 未通过。期望行数 23 无法验证。

## Step 2 监督首跑

未执行。原因: Step 1 manifest 缺失, 按红线停止。

未产生 commentary dry-run / market dry-run / derived preview 数字。未执行 `derived_signals apply`, 未执行 `produce_and_push`, 未写 vault。

## Step 3 投影验证

未执行。原因: Step 1 未通过, Step 2 未完成。

未产生 `commentary_count` / `relation_count`。

## Step 4 安装 03:00 cron

未执行。原因: 信号链首跑未通过前不接 cron。

## Step 5 哨兵新口径实测

未执行。原因: 前置部署链已中止。

## 当前状态与建议

- 服务器 `/root/policy-pipeline-src` 已更新到 `c638cef`。
- 现有 Docker 镜像 import 闸通过, 但未重建镜像。
- `/root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl` 未初始化。
- 未执行任何信号链 apply / produce_and_push, 未安装 03:00 cron, 未触发 QR relay。

推荐下一步: 先补齐或确认 `market_intel_manifest.jsonl` 的来源并合入/分发到服务器可用路径, 再从 Step 1 重新开始。不要跳过 Step 1 直接跑 Step 2, 因为 market dry-run 的 Done Gate 依赖该 manifest。
