# Codex 交接:S2 部署收尾(W0 飞书通道 + W1 评论线监督首跑 + cron 上线)

**目标**:把 S2「VPS 单生产者」从"代码已合 main、基础设施已就位"推进到"评论线全自动跑起来":飞书告警通道接通验证 → W1 评论 ingest 监督首跑(写真 vault + push + 投影)→ 接 4 条 cron → Mac 哨兵下线。

**背景**:代码全集已合 main(PR #6,`d7eb716`)。服务器(阿里云东京 `root@8.216.59.173`,Mac 上用 `ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`)已就位:镜像构建好、wewe-rss 入 platform-net、`/etc/policy-pipeline/{models,commentary,pipeline}.env` 齐、vault git 身份+可写 remote 验过、openclaw 2026.6.5 gateway 已常驻(systemd user + linger)、feishu 插件已装且 WebSocket 已连(bot open_id 已解析)、哨兵 venv `/root/policy-sentinel-venv` 备好。配套文档:`docs/runbooks/s2-vps-cron.md`(crontab 全文照抄源)、spec/plan 在 `docs/superpowers/`。

**纪律(红线,违者中止)**:
- 凭据值**不打印、不进 git**(env 文件只看键名核验:`grep -oE '^[A-Z_]+=' <file>`)。
- 微信 token 不碰;wewe-rss 的 Mac 容器保持**停**(别 start)。
- 仓库工作区的未跟踪文件(`docs/2026-06-09-*`、`docs/runbooks/fetch-proxy-*`、`scripts/service/fetch_proxy_health.py` 等)和未提交的 `OPERATIONS.md` 改动是别条线的,**绝不 add/commit/改动**。
- `/root/safety-platform`、`platform-*` 容器不碰。
- vault 写入只经 `produce_and_push`(白名单守卫),**绝不手工在 /root/policy-vault 里 git add/commit**。
- 09:00(L1 政策)和 09:30(L2)两条 cron **保持注释**,那是 W2/W3 的事。
- 任何一步验证不过:**停下、原样报告输出**,不要即兴绕。

---

## Step 1 · 飞书配对 approve + notify.env

VPS 上 openclaw 配对请求已在队列(用户已 DM 新机器人):code `NU84W9B5`,userId `ou_7cad4512615d4b64a509c7416ba91984`。

```bash
ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173
openclaw pairing list feishu          # 确认请求还在;若过期 → 停下报告(用户需重新 DM 拿新码)
openclaw pairing approve feishu NU84W9B5
umask 077
cat > /etc/policy-pipeline/notify.env <<'EOF'
OPENCLAW_CHANNEL=feishu
OPENCLAW_ACCOUNT=main
OPENCLAW_IM_TARGET=ou_7cad4512615d4b64a509c7416ba91984
OPENCLAW_COMMAND=/usr/local/bin/openclaw
EOF
chmod 600 /etc/policy-pipeline/notify.env
```

## Step 2 · 通道双验证(以飞书真收到为准)

```bash
set -a; . /etc/policy-pipeline/notify.env; set +a
# ① openclaw 直发
"$OPENCLAW_COMMAND" message send --channel "$OPENCLAW_CHANNEL" --account "$OPENCLAW_ACCOUNT" \
  --target "$OPENCLAW_IM_TARGET" --message "[policy-pipeline] 验证①: VPS openclaw 直发" --json
# ② notify python 路径(host /usr/bin/python3,专测 cron 实际走的链)
cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.notify "[S2] 验证②: notify python 路径"
```

判据:① 返回 JSON 成功;② 打印 `notify sent=True`;**两条消息用户飞书都收到**(报告里请用户确认)。任一不过 → 停。

## Step 3 · W1 评论线监督首跑(照 runbook §2)

```bash
set -a; . /etc/policy-pipeline/notify.env; . /etc/policy-pipeline/commentary.env; set +a
cd /root/policy-pipeline-src
docker compose -f docker-compose.server.yml run --rm -e WEWE_FEED_URL -e WEWE_AUTH_CODE \
  policy-producer python -m scripts.l1_collect.commentary_ingest.run \
  --feed-url "$WEWE_FEED_URL" --auth-code "$WEWE_AUTH_CODE" \
  --vault-dir /vault --state-dir /state --since 2026-06-06
```

预期:打印 summary JSON(`feed_count/ingested/...`;缺口约数日,ingested 估计两位数)。`coverage_warning` 首跑可能误报,记录即可。

```bash
/usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
  --whitelist 0_raw/commentaries/ --message "l1(commentary): W1 supervised first run"
```

预期 exit 0、打印 `pushed N paths`。exit 4(白名单外改动)/exit 5(push 失败)→ 停,报告 stderr。

**验证四件**:
```bash
git -C /root/policy-vault log --oneline -2      # ① 新 commit 在,作者 policy-pipeline-vps
git -C /root/policy-vault status --short        #    且树干净
git -C /root/policy-vault rev-parse HEAD origin/main   # ② 两值相同(已推上 GitHub)
# ③ 投影
cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm \
  policy-pipeline python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1
head -c 300 /root/policy-pipeline-state/last_sync_run.json; echo   # errors=[] 且 commentary 计数增长
# ④ 飞书静默(无告警消息)= 健康
```

## Step 4 · 接 4 条 cron(先核 TZ)

```bash
timedatectl | grep "Time zone"   # 若非 Asia/Shanghai(CST):下面时刻全部 -8h 换算(runbook 纪律)
```

从 `docs/runbooks/s2-vps-cron.md` §1 **原样复制**这 4 条进 `crontab -e`(root):07:30 评论 ingest、09:30 QR relay 哨兵、`0 */6` token 检测、10:00 投影。**09:00 与 09:30-L2 两条注释行也可一并贴入但保持注释**。既有 `0 21 * * *` sync_tick 行**保留不动**。

装完核验:`crontab -l | grep -c policy` 应 ≥5(4 新 + 1 既有),且 `/var/lock/` 可写(flock 首跑自建)。

## Step 5 · Mac 哨兵下线(在 Mac 上)

```bash
launchctl unload ~/Library/LaunchAgents/com.zayn.policy.wewe-qr-relay-daily.plist
launchctl list | grep wewe-qr || echo "mac sentinel unloaded ✓"
```

(Mac 的 wewe-rss 容器本就停着,确认别把它带起来:`docker ps | grep wewe` 应为空。)

---

## 回报格式

逐 Step:执行的命令 + 关键输出(env 值打码)。重点:Step 2 两条消息是否双达、Step 3 的 summary JSON 与四件验证结果、Step 4 的 crontab 终态(`crontab -l` 全文)、遇到的任何偏差。报告落 `docs/handoffs/2026-06-10-codex-s2-w0w1-report.md`(不含任何凭据值)。
