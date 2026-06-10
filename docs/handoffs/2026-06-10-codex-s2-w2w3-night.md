# Codex 交接:S2 今晚全开(W3 政策线验证轮 + W2 L2 首跑 + 解注释 cron)

**目标**:今晚把政策 L1 与 L2 两条线监督验证后解禁,使明早 6/11 成为三线(评论+政策+L2)全自动的第一个早晨。

**背景**:评论线已全自动(今早上线,W1)。服务器:阿里云东京,Mac 上 `ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`;repo `/root/policy-pipeline-src`,vault `/root/policy-vault`。两条 cron(09:00 L1 / 09:30 L2)现注释在 root crontab。**l2_queue 目前为空——必须先跑 L1(入队)再跑 L2(消费),顺序不可颠倒。** models.env 缺 ANTHROPIC_* 两键,Step 0 落位。

**纪律(红线,违者中止)**:
- 凭据值**不打印、不进 git**(键名核验只用 `grep -oE '^[A-Z_]+=' <file>`)。
- vault 写只经 `produce_and_push`;**绝不**手工在 /root/policy-vault 里 git add/commit。
- 手跑生产命令必须持 flock 锁(与 cron 同一把,见各 Step 命令)。
- 任一 gate 不过 / 命令报错:**停下、原样报告(值打码),绝不在失败状态下解注释 cron**。
- `/root/safety-platform`、`platform-*` 容器、Mac 的 wewe-rss 容器(保持停)、repo 工作区未跟踪文件,一律不碰。
- 若执行横跨 21:00:等既有 sync_tick cron 跑完(几分钟)再做 produce_and_push,避免与兜底拉取交错。

---

## Step 0 · models.env 补 ANTHROPIC_*(值盲)

先查重:`grep -q '^ANTHROPIC_API_KEY=' /etc/policy-pipeline/models.env && echo 已存在` ——已存在则跳过 append,直接做容器视角验证。

```bash
umask 077
[ -n "$(tail -c1 /etc/policy-pipeline/models.env)" ] && echo >> /etc/policy-pipeline/models.env
grep '^MINIMAX_API_KEY=' /etc/policy-pipeline/models.env | sed 's/^MINIMAX_API_KEY=/ANTHROPIC_API_KEY=/' >> /etc/policy-pipeline/models.env
echo 'ANTHROPIC_BASE_URL=<BASE_URL>' >> /etc/policy-pipeline/models.env   # ← 用户提供的 MiniMax anthropic 兼容 base URL
chmod 600 /etc/policy-pipeline/models.env
grep -oE '^[A-Z_]+=' /etc/policy-pipeline/models.env    # 应比之前多 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL 两键
# 容器视角验证(URL 非密可打印,key 只打 bool):
cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -c "import os; print('key_set=', bool(os.environ.get('ANTHROPIC_API_KEY')), 'base=', os.environ.get('ANTHROPIC_BASE_URL'))"
```

判据:`key_set= True` 且 base 显示用户给的 URL。

## Step 1 · W3 政策线 dry-run(→ 用户 gate ①)

```bash
( /usr/bin/flock -w 600 9; set -a; . /etc/policy-pipeline/notify.env; set +a; \
  cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.l1_collect.run_incremental --vault-dir /vault/0_raw/policies \
    --l2-queue /state/l2_queue.jsonl --dry-run \
) 9>/var/lock/policy-pipeline-producer.lock
```

把输出的变更集摘要(渠道、条数)贴给用户。**用户确认合理才进 Step 2。**
注意:抓政府站可能较慢,耐心等;个别渠道 fetch_error 记录即可(长尾代理是后续决策),全渠道挂死才算异常。

## Step 2 · W3 真跑 + 质量抽查(→ 用户 gate ②)+ push

```bash
( /usr/bin/flock -w 600 9; set -a; . /etc/policy-pipeline/notify.env; set +a; \
  cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.l1_collect.run_incremental --vault-dir /vault/0_raw/policies \
    --l2-queue /state/l2_queue.jsonl \
) 9>/var/lock/policy-pipeline-producer.lock
git -C /root/policy-vault status --short | head -30    # 列新增文件
```

用户挑 2–3 份新入库 policy,`sed -n '1,40p' '/root/policy-vault/0_raw/policies/<文件名>'` 贴头部给用户抽查。**用户点头才 push**:

```bash
/usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
  --whitelist 0_raw/policies/,0_raw/commentaries/ --message "l1(policy): W3 supervised verification run"
wc -l /root/policy-pipeline-state/l2_queue.jsonl    # 应 >0(L2 有活干了)
```

预期 exit 0、打印 pushed N paths;exit 4(白名单外改动)/ exit 5(push 失败)→ 停,报 stderr。

## Step 3 · W2 L2 监督首跑(MiniMax 生成 + deepseek judge)+ push

```bash
( /usr/bin/flock -w 600 9; set -a; . /etc/policy-pipeline/notify.env; set +a; \
  cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.service.run_l2 --vault /vault --state-dir /state \
    --gen-model MiniMax-M2.7-highspeed --gen-provider anthropic \
    --judge-model deepseek-v4-flash --judge-provider openai \
) 9>/var/lock/policy-pipeline-producer.lock
```

判据:输出 drained/succeeded/failed 计数,**failed=0 通过**;有 failed → 停,贴错误详情(脱敏)。首跑常见问题:base URL 形态不对(401/404/连接错)→ 停下报告,**别自行改 URL**。

通过后:

```bash
/usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
  --whitelist 1_extracted/,_meta/business_view/,2_crystallized/ --message "l2: W2 supervised first run"
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

判据:`errors=[]`;synced 计数 > 761(今晨基线);HEAD == origin/main;vault log 出现今晚 2–3 个机器 commit(作者 policy-pipeline-vps)。请用户确认飞书静默(无告警)。

## Step 5 · 解注释两条 cron(全部 gate 通过后才做)

```bash
crontab -l | sed 's/^#0 9 /0 9 /; s/^#30 9 /30 9 /' | crontab -
crontab -l | grep -v '^#' | grep -c policy    # 应 7(此前 5 + 新开 2)
```

(sed 只动行首 `#0 9 ` / `#30 9 ` 的两条注释 cron,不会碰 09:30 QR 哨兵那条未注释行、也不会碰 `# 09:00 …` 这类说明注释。)

---

## 回报格式

逐 Step:执行的命令 + 关键输出(凭据值打码)。重点:Step 1 变更集摘要、Step 2 ingest summary 与 push 结果、Step 3 的 drained/succeeded/failed、Step 4 的 last_sync_run 数字与 vault log、Step 5 的 crontab 终态。报告落 `docs/handoffs/2026-06-10-codex-s2-w2w3-report.md`(不含任何凭据值)。
