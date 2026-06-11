# WP-6b 闭环巡检部署报告

日期: 2026-06-11

## 结论

已完成服务器侧部署到 `main@74ff6d7`。`closure_audit --dry-run` 返回 2 项违规且 `EXIT=1`。

核验后,2 项均为 2026-06-11 之前的 vault 历史 commit,符合交接中"已知窗口效应"停机条件。因此本次已按要求中止:

- 未执行无 `--dry-run` 的真跑。
- 未安装 10:45 `closure_audit` cron。
- 未写 vault,未写 state。

建议下一步:由 Claude 按交接建议做全局规则修复,给 `closure_audit` 增加日期截断/窗口边界后再重新部署监督跑。

## Step 0 · 部署

命令:

```bash
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main
```

服务器输出:

```text
From github-pipeline:ZaynShao/policy-analysis-pipeline
 * branch            main       -> FETCH_HEAD
 + 50e5de0...74ff6d7 main       -> origin/main  (forced update)
HEAD is now at 74ff6d7 service: add closure audit巡检
74ff6d7
```

结果: HEAD 符合预期 `74ff6d7`。

## Step 1 · 监督跑 dry-run

命令:

```bash
cd /root/policy-pipeline-src
/usr/bin/python3 -m scripts.service.closure_audit --vault /root/policy-vault --state-dir /root/policy-pipeline-state --dry-run; echo "EXIT=$?"
```

完整输出原文:

```text
[S2] 闭环巡检异常 2 项:
- 产物路径非 VPS 作者: cf2f824f2592 ZaynShao 0_raw/_archive/policies/README.md
- 产物路径非 VPS 作者: a6fb3c09c531 ZaynShao 1_extracted/relations/_archive_a_commentary_migration.jsonl
EXIT=1
```

判定: 非全绿,进入违规核对。

### 违规 commit 日期核验

工程仓服务器 checkout 为 depth=1,无法解析历史 commit;改在 `/root/policy-vault` 中核验。

```text
cf2f824f2592dc4d5d8abb02378a1ec652dca25e	2026-06-07T19:27:33+08:00	ZaynShao	data(l1): backfill 净+156政策 + 18官方解读转政策评论 + 退2污染 (2026-06-07 Task12收口)
a6fb3c09c531e31a04941701b8be4951cb884039	2026-06-06T21:00:03+08:00	ZaynShao	③-apply:关系层换新视图(459反链页+canonical API,换掉5/8+5/12 stale)
```

两项均早于 2026-06-11,且不是 state 活性类异常。按交接纪律,判定为已知窗口效应,停下报告。

## Step 2 · 10:45 cron

未执行。原因: Step 1 dry-run 未全绿。

runbook §1 的 10:45 行已核对如下,但未写入 crontab:

```cron
45 10 * * * cd /root/policy-pipeline-src && (set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.closure_audit --vault /root/policy-vault --state-dir /root/policy-pipeline-state) >> /var/log/policy-pipeline/closure_audit.log 2>&1
```

## 门禁状态

- 凭据值: 未打印。
- vault/state: 未写。
- `safety-platform` / `platform-*` / `tyo-prod` / Mac wewe: 未触碰。
- cron: 未安装。

## 续跑

日期: 2026-06-11

结论: **完成 Step 0→2**。服务器 checkout 已更新到 `main@1d0b91d`, `closure_audit --dry-run` 全绿,无 `--dry-run` 真跑返回健康结果,10:45 `closure_audit` cron 已安装且计数为 1。

### Step 0 · 部署

命令:

```bash
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main && git rev-parse --short HEAD
```

服务器输出:

```text
From github-pipeline:ZaynShao/policy-analysis-pipeline
 * branch            main       -> FETCH_HEAD
 + 74ff6d7...1d0b91d main       -> origin/main  (forced update)
HEAD is now at 1d0b91d fix(service): exempt pre-cutoff vault authors
1d0b91d
```

结果: HEAD 符合预期 `1d0b91d`。

### Step 1 · 监督跑 dry-run

命令:

```bash
cd /root/policy-pipeline-src
/usr/bin/python3 -m scripts.service.closure_audit --vault /root/policy-vault --state-dir /root/policy-pipeline-state --dry-run; echo "EXIT=$?"
```

完整输出原文:

```text
{"ok": true, "checked": {"state_paths": 6, "vault_product_commits": 12}}
EXIT=0
```

判定: 全绿,上次两条历史 commit 假阳性已消失。

### Step 1b · 真跑健康确认

命令:

```bash
cd /root/policy-pipeline-src
/usr/bin/python3 -m scripts.service.closure_audit --vault /root/policy-vault --state-dir /root/policy-pipeline-state; echo "EXIT=$?"
```

输出:

```text
{"ok": true, "checked": {"state_paths": 6, "vault_product_commits": 12}}
EXIT=0
```

判定: 健康路径通过,未触发异常告警路径。

### Step 2 · 10:45 cron

安装 runbook §1 的 10:45 行:

```cron
45 10 * * * cd /root/policy-pipeline-src && (set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.closure_audit --vault /root/policy-vault --state-dir /root/policy-pipeline-state) >> /var/log/policy-pipeline/closure_audit.log 2>&1
```

核验输出:

```text
before=0
after=1
```

结果: root crontab 中 `closure_audit` 计数为 1。

### 门禁状态

- 凭据值: 未打印,未写入报告。
- vault/state: 巡检只读;本轮未写 vault,未写 state。
- `safety-platform` / `platform-*` / `tyo-prod` / Mac wewe: 未触碰。
- cron: 已安装 10:45 `closure_audit` 行。

当前仍在 WP-6b 巡检部署闭环。原则/门禁仍生效:巡检只读、raw 不可变、dry-run before apply 纪律未被放宽、凭据不进 git。

建议下一步: 明天 10:45 后检查 `/var/log/policy-pipeline/closure_audit.log` 与飞书是否无异常告警;若自动巡检连续静默,WP-6 可视为进入日常监督态。
