# Codex 交接:S2 今晚全开(W3 政策线验证轮 + W2 L2 首跑 + 解注释 cron)

> **2026-06-10 决策更新(覆盖原计划)**:
> 1. **MiniMax 不订阅(商务决策),永久移除**。L2 的 **gen + judge 都用 deepseek-v4-flash,走 openai 兼容路径(`--gen-provider openai` / `--judge-provider openai`),读 `OPENAI_*`,不需要 `ANTHROPIC_*`**。
> 2. **先修扫描并发再跑**:本手册的前置 = 先完成 `docs/handoffs/2026-06-10-codex-scan-concurrent.md`(L1 扫描段并发化 + 服务器重建镜像),再从本手册 **Step 2** 起。
> 3. Step 0(models.env)与 Step 1(dry-run)**已完成**,见下方标注;真正要执行的是 Step 2→5。

**目标**:把政策 L1 与 L2 两条线监督验证后解禁,使明早 6/11 成为三线(评论+政策+L2)全自动的第一个早晨。

**背景**:评论线已全自动(W1)。服务器:阿里云东京,Mac 上 `ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`;repo `/root/policy-pipeline-src`,vault `/root/policy-vault`。两条 cron(09:00 L1 / 09:30 L2)现注释在 root crontab。

**纪律(红线,违者中止)**:
- 凭据值**不打印、不进 git**(键名核验只用 `grep -oE '^[A-Z_]+=' <file>`)。
- vault 写只经 `produce_and_push`;**绝不**手工在 /root/policy-vault 里 git add/commit。
- 手跑生产命令必须持 flock 锁(与 cron 同一把,见各 Step 命令)。
- 任一 gate 不过 / 命令报错:**停下、原样报告(值打码),绝不在失败状态下解注释 cron**。
- `/root/safety-platform`、`platform-*` 容器、Mac 的 wewe-rss 容器(保持停)、repo 工作区未跟踪文件,一律不碰。
- 若执行横跨 21:00:等既有 sync_tick cron 跑完(几分钟)再做 produce_and_push,避免与兜底拉取交错。

---

## Step 0 · models.env(✅ 已完成)

用户已把 **deepseek 的 key/base 写入 `OPENAI_API_KEY` / `OPENAI_BASE_URL`**(deepseek 用 openai 兼容协议)。容器视角已验:`openai_key_set=True` / `base_set=True` / `judge_model=deepseek-v4-flash`。**不需要 ANTHROPIC_***(MiniMax 已弃)。无需再动 models.env。

## Step 1 · L1 dry-run(✅ 已在旧串行版完成)

旧串行版 dry-run 结果:`channels_run=165`、`total_scanned=378`,**cand 文件留有 ~66 条去重后候选**(`total_ingested=0` 是 dry-run 写死值,非"无新政策")。⇒ Step 2 真跑确有约 66 条候选要 fetch+gate+ingest。
**并发修复 + 服务器重建镜像后**,可选再跑一次快 dry-run 确认 <10 min 且无 fetch_error,然后进 Step 2。

## Step 2 · W3 真跑 + 质量抽查(→ 用户 gate)+ push

```bash
( /usr/bin/flock -w 600 9; set -a; . /etc/policy-pipeline/notify.env; set +a; \
  cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.l1_collect.run_incremental --vault-dir /vault/0_raw/policies \
    --l2-queue /state/l2_queue.jsonl \
) 9>/var/lock/policy-pipeline-producer.lock
git -C /root/policy-vault status --short | head -40    # 列新增文件(预期 ~数十条新 policy)
```

用户挑 2–3 份新入库 policy,`sed -n '1,40p' '/root/policy-vault/0_raw/policies/<文件名>'` 贴头部给用户抽查。**用户点头才 push**:

```bash
/usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
  --whitelist 0_raw/policies/,0_raw/commentaries/ --message "l1(policy): W3 supervised verification run"
wc -l /root/policy-pipeline-state/l2_queue.jsonl    # 应 >0(L2 有活干了)
```

预期 exit 0、打印 pushed N paths;exit 4(白名单外改动)/ exit 5(push 失败)→ 停,报 stderr。

## Step 3 · W2 L2 监督首跑(deepseek gen + deepseek judge)+ push

```bash
( /usr/bin/flock -w 600 9; set -a; . /etc/policy-pipeline/notify.env; set +a; \
  cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.service.run_l2 --vault /vault --state-dir /state \
    --gen-model deepseek-v4-flash --gen-provider openai \
    --judge-model deepseek-v4-flash --judge-provider openai \
) 9>/var/lock/policy-pipeline-producer.lock
```

判据:输出 `{processed, ok, failed, skipped}` JSON,**failed=0 通过**;有 failed → 停,贴错误详情(脱敏)。首跑常见问题:deepseek 端点 401/404/连接错 → 停下报告(多半 OPENAI_BASE_URL/KEY 形态问题),**别自行改值**。

通过后:

```bash
/usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
  --whitelist 1_extracted/,_meta/business_view/,2_crystallized/ --message "l2: W2 supervised first run (deepseek)"
```

## Step 4 · 投影 + 终态验证

```bash
( /usr/bin/flock -w 600 9; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm \
  policy-pipeline python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1 \
) 9>/var/lock/policy-pipeline-producer.lock
head -c 400 /root/policy-pipeline-state/last_sync_run.json; echo
git -C /root/policy-vault log --oneline -5
git -C /root/policy-vault rev-parse HEAD origin/main
```

判据:`errors=[]`;synced 计数 > 761(今晨基线);HEAD == origin/main;vault log 出现今晚机器 commit(作者 policy-pipeline-vps)。请用户确认飞书静默(无告警)。

## Step 5 · 解注释两条 cron + 把 L2 行改成 deepseek(全部 gate 通过后才做)

**关键**:服务器上注释的 L2 cron 行仍写着 MiniMax/anthropic,直接解注释会失败。必须**先改 gen 参数为 deepseek/openai,再解注释**:

```bash
crontab -l \
  | sed 's#--gen-model MiniMax-M2.7-highspeed --gen-provider anthropic#--gen-model deepseek-v4-flash --gen-provider openai#' \
  | sed 's/^#0 9 /0 9 /; s/^#30 9 /30 9 /' \
  | crontab -
# 核验:
crontab -l | grep -v '^#' | grep -c policy            # 应 7(此前 5 + 新开 2)
crontab -l | grep -- '--gen-model'                    # 应显示 deepseek-v4-flash --gen-provider openai,无 MiniMax/anthropic
```

(sed 第一句替换 L2 行 gen 参数;第二句只解注释行首 `#0 9 ` / `#30 9 ` 两条 cron,不碰 09:30 QR 哨兵未注释行、也不碰说明性注释。)

---

## 回报格式

逐 Step:执行的命令 + 关键输出(凭据值打码)。重点:Step 2 的新增 policy 数与 push 结果、Step 3 的 `{processed/ok/failed}`、Step 4 的 last_sync_run 数字与 vault log、Step 5 的 crontab 终态(`crontab -l` 全文,确认 L2 行 deepseek 且无 MiniMax)。报告续写 `docs/handoffs/2026-06-10-codex-s2-w2w3-report.md`(不含任何凭据值)。
