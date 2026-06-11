# S2 · VPS 单生产者 cron 接线 runbook

> 配套:`docs/superpowers/specs/2026-06-10-s2-vps-single-producer-design.md`(spec)
> 与 `docs/superpowers/plans/2026-06-10-s2-vps-single-producer.md`(plan,W0–W4 波次)。
> 本文是**部署时照抄的接线文本 + 验证命令**。改节奏只动本文 crontab 段。

## 0. 前置 checklist(全过才接 cron)

| # | 项 | 验法 |
|---|---|---|
| 1 | main 已合本分支,服务器 `git reset --hard origin/main` + `docker compose build` | `docker run --rm policy-pipeline:latest python -c "import trafilatura, bs4"` |
| 2 | `/etc/policy-pipeline/models.env`(0600):OPENAI_API_KEY / OPENAI_BASE_URL = deepseek(L2 gen+judge 都走 openai 兼容,无需 ANTHROPIC_*;MiniMax 已弃)/ 可选 FIRECRAWL/TAVILY | `docker compose -f docker-compose.server.yml config -q` 不报缺文件 |
| 3 | `/etc/policy-pipeline/notify.env`(0600):OPENCLAW_CHANNEL / OPENCLAW_ACCOUNT / OPENCLAW_IM_TARGET / OPENCLAW_COMMAND;openclaw 已装 VPS | 发测试消息(plan Task 0.3 Step 验证命令),飞书收到;再 `cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.notify "[S2] notify python 路径连通测试"` ——输出 `notify sent=True` 且飞书收到(host python 缺 requests 时 send_text 会静默 False,此步专测 python 路径) |
| 4 | `/etc/policy-pipeline/commentary.env`(0600):WEWE_AUTH_CODE / WEWE_FEED_URL=`http://wewe-rss:4000/feeds/all.json?limit=400`(容器视角)/ WEWE_BASE_URL=`http://127.0.0.1:4000`(host 哨兵视角)/ WEWE_DB_PATH=`/root/wewe-rss/data/wewe-rss.db` | — |
| 5 | wewe-rss 容器已加入 `safety-platform_platform-net`(plan Task 0.5) | 容器互通 curl 200 |
| 6 | vault git 身份 + 可写 remote(github-vault-rw) | `git -C /root/policy-vault config user.name` 非空 |
| 7 | 哨兵 venv:`python3 -m venv /root/policy-sentinel-venv && /root/policy-sentinel-venv/bin/pip install requests qrcode pillow trafilatura beautifulsoup4 pyyaml`(trafilatura/yaml 是 `--check-token` 经 run.py 顶层 import 连带需要;**pillow 是 qrcode 出 PNG 必需**——2026-06-11 实锤:漏装则推码在 render_qr_png 处 ModuleNotFoundError,QR 永远到不了 IM) | venv python `-c "import requests, qrcode, trafilatura; from PIL import Image"` |
| 8 | **TZ 确认**:`timedatectl` 看服务器时区。下方时刻按 **CST** 写;若系统是 UTC,全部 -8h 换算后再进 crontab | — |
| 9 | channel catalog 已随 git 到位:`ls /root/policy-pipeline-src/state/T1_channels/channel_catalog.yaml`(它是 git-tracked,容器经 `/app/state` 挂载可见) | — |

## 1. crontab(root)

纪律:
- **flock 串行化**:所有写 vault / 写 L2 队列的行共持 `/var/lock/policy-pipeline-producer.lock`(`flock -w 7200` 等待不跳过)——评审定论:l2_queue 是无锁读改写,07:30/09:00/09:30/10:00 必须串行;慢 L1 自然把 L2 推后。
- **代理纪律**:`POLICY_FETCH_PROXY_URL` 只许出现在 09:00 L1 行内 `-e` 注入(W3 按需解开),其它行绝不 source fetch-proxy.env。
- **`--since 2026-06-06` 是固定回填边界**(vault 评论存量边界 2026-06-07 往前推一天对冲时区),写死在 cron 行,**不进 commentary.env**(防变成漂移配置毁掉 coverage_warning 信号)。
- **`--feed-timeout 600`**:wewe-rss 冷缓存时 fulltext limit=400 的 feed 生成可 >120s(实测热缓存 0.2s);每日 07:00 discovery 后缓存变冷,默认 120s 必超时。
- **03:00 信号链 state**:`/state/commentary_signals/nightly`、`/state/market_intel_signals/nightly`、`/state/derived_signals/nightly` 是每晚覆盖重建的中间状态目录,不作为长期账本。
- **03:00/03:30 脚本化**:crontab 只保留短行,逻辑唯一真相源在 `/root/policy-pipeline-src/scripts/service/signals_nightly.sh` 和 `/root/policy-pipeline-src/scripts/service/contexts_nightly.sh`;服务器临时脚本 `/root/policy-pipeline-state/bin/commentary_signals.run_nightly.sh` 待 WP-4b 移除。
- **03:30 上下文链 state**:`/state/signal_context/nightly`、`/state/analysis_layer/nightly`、`/state/analysis_layer/nightly_inventory` 是每晚覆盖重建的中间状态目录;产物在 `/state`,不写 vault,无 push 环节。
- 失败告警:行内 `|| notify`(泛化)+ produce_and_push 内部告警(带细节),可能双发,可接受。

```cron
SHELL=/bin/bash
# ───────── S2 单生产者编排(时刻=CST;UTC 机器全部 -8h)─────────

# 02:00 ③关系增量(容器 LLM judge;增量=新pid×存量;produce_and_push 白名单只放 relations)
0 2 * * * ( /usr/bin/flock -w 7200 9 || { set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.notify "[S2] producer 锁等待超时(7200s),本轮跳过"; exit 1; }; set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.service.relations_increment run --vault /vault --state-dir /state --judge-model deepseek-v4-flash --judge-provider openai && /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault --whitelist 1_extracted/relations/ --message "l2(relations): nightly increment" || /usr/bin/python3 -m scripts.service.notify "[S2] 02:00 关系增量失败,查 relations.log" ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/relations.log 2>&1

# 03:00 ③信号链(commentary + market intel dry-run → derived preview/apply → produce_and_push 白名单只放 signals)
0 3 * * * /root/policy-pipeline-src/scripts/service/signals_nightly.sh >> /var/log/policy-pipeline/signals.log 2>&1

# 03:30 ④上下文链(signal context + analysis context + relation inventory;只写 /state,无 push)
30 3 * * * /root/policy-pipeline-src/scripts/service/contexts_nightly.sh >> /var/log/policy-pipeline/contexts.log 2>&1

# 07:30 评论 ingest(容器,经 platform-net 访问 wewe-rss)→ vault → push
30 7 * * * ( /usr/bin/flock -w 7200 9 || { set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.notify "[S2] producer 锁等待超时(7200s),本轮跳过"; exit 1; }; set -a; . /etc/policy-pipeline/notify.env; . /etc/policy-pipeline/commentary.env; set +a; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm -e WEWE_FEED_URL -e WEWE_AUTH_CODE policy-producer python -m scripts.l1_collect.commentary_ingest.run --feed-url "$WEWE_FEED_URL" --auth-code "$WEWE_AUTH_CODE" --vault-dir /vault --state-dir /state --since 2026-06-06 --feed-timeout 600 && /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault --whitelist 0_raw/commentaries/ --message "l1(commentary): daily ingest" || /usr/bin/python3 -m scripts.service.notify "[S2] 07:30 评论 ingest 失败,查 ingest.log" ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/ingest.log 2>&1

# 09:00 L1 政策增量(容器)→ vault → push → L2 队列(W3 验证后解开注释)
#0 9 * * * ( /usr/bin/flock -w 7200 9 || { set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.notify "[S2] producer 锁等待超时(7200s),本轮跳过"; exit 1; }; set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.l1_collect.run_incremental --vault-dir /vault/0_raw/policies --l2-queue /state/l2_queue.jsonl && /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault --whitelist 0_raw/policies/,0_raw/commentaries/ --message "l1(policy): daily incremental" || /usr/bin/python3 -m scripts.service.notify "[S2] 09:00 L1 失败,查 l1.log" ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/l1.log 2>&1
# ↑ W3 若长尾渠道持续 fetch_error 需代理,把 docker compose run 段加:--rm 后插 `-e POLICY_FETCH_PROXY_URL="$(. /etc/policy-pipeline/fetch-proxy.env; echo $POLICY_FETCH_PROXY_URL)"`(仅此一行,纪律)

# 09:30 L2 drain(容器)→ vault → push(W2 验证后解开注释)
#30 9 * * * ( /usr/bin/flock -w 7200 9 || { set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.notify "[S2] producer 锁等待超时(7200s),本轮跳过"; exit 1; }; set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.service.run_l2 --vault /vault --state-dir /state --gen-model deepseek-v4-flash --gen-provider openai --judge-model deepseek-v4-flash --judge-provider openai && /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault --whitelist 1_extracted/,_meta/business_view/,2_crystallized/ --message "l2: daily derive" || /usr/bin/python3 -m scripts.service.notify "[S2] 09:30 L2 失败,查 l2.log" ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/l2.log 2>&1

# 09:55 死信增长告警(host python,只读死信+自身state,不需 flock)
55 9 * * * set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.deadletter_alert --state-dir /root/policy-pipeline-state >> /var/log/policy-pipeline/deadletter.log 2>&1

# 周日 08:30 死信 sweep 回队(写队列,必须持 producer flock;回队项当日 09:30 L2 顺手消化)
30 8 * * 0 ( /usr/bin/flock -w 7200 9 || exit 1; set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && /usr/bin/python3 -m scripts.service.deadletter_sweep --state-dir /root/policy-pipeline-state ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/deadletter.log 2>&1

# 10:00 投影 heng-pg(消费侧 ro 服务;持锁防读到产线写一半的 vault)
0 10 * * * ( /usr/bin/flock -w 7200 9 || { set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.notify "[S2] producer 锁等待超时(7200s),本轮跳过"; exit 1; }; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-pipeline python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1 || { set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.notify "[S2] 10:00 投影失败"; } ) 9>/var/lock/policy-pipeline-producer.lock >> /var/log/policy-pipeline/sync_tick.log 2>&1

# 09:30 QR relay 哨兵(host venv;token 失效→openclaw 推码→扫后 account.add 自动落库)
30 9 * * * set -a; . /etc/policy-pipeline/notify.env; . /etc/policy-pipeline/commentary.env; set +a; cd /root/policy-pipeline-src && /root/policy-sentinel-venv/bin/python -m scripts.l1_collect.commentary_ingest.qr_relay.daily_check --db-path "$WEWE_DB_PATH" --qr-dir /root/policy-pipeline-state/wewe_qr --target "$OPENCLAW_IM_TARGET" >> /var/log/policy-pipeline/qr_relay.log 2>&1

# 每 6h token 检测(读 sqlite,免费;失效→飞书文字,QR 哨兵 09:30 会推码)
0 */6 * * * set -a; . /etc/policy-pipeline/notify.env; . /etc/policy-pipeline/commentary.env; set +a; cd /root/policy-pipeline-src && /root/policy-sentinel-venv/bin/python -m scripts.l1_collect.commentary_ingest.run --check-token --db-path "$WEWE_DB_PATH" >> /var/log/policy-pipeline/token.log 2>&1 || /usr/bin/python3 -m scripts.service.notify "[S2] wewe token 失效,QR 哨兵将于 09:30 推码"

# 21:00 sync_tick 兜底(S1 既有,不动:外部变更拉取 + 防误删守卫)
```

## 2. W1 监督首跑(接 07:30 cron 之前,人在场手跑一遍)

```bash
set -a; . /etc/policy-pipeline/notify.env; . /etc/policy-pipeline/commentary.env; set +a
cd /root/policy-pipeline-src
docker compose -f docker-compose.server.yml run --rm -e WEWE_FEED_URL -e WEWE_AUTH_CODE \
  policy-producer python -m scripts.l1_collect.commentary_ingest.run \
  --feed-url "$WEWE_FEED_URL" --auth-code "$WEWE_AUTH_CODE" \
  --vault-dir /vault --state-dir /state --since 2026-06-06 --feed-timeout 600
# 看 summary JSON 后:
/usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
  --whitelist 0_raw/commentaries/ --message "l1(commentary): W1 supervised first run"
```

验证四件:① `git -C /root/policy-vault log -1` 出现该 commit 且 `git -C /root/policy-vault status` 干净;② GitHub origin/main 同 HEAD;③ 跑一次 10:00 投影命令,`/root/policy-pipeline-state/last_sync_run.json` errors=[];④ 飞书无告警。
已知一次性现象:**首跑 coverage_warning 可能误报**(--since 把本可计为 duplicates 的老条目滤掉了),记录即可,连续出现才是真信号。

## 3. 日常验证(次日)

```bash
tail -5 /var/log/policy-pipeline/ingest.log     # summary JSON + pushed
git -C /root/policy-vault log --oneline -3       # 机器 commit 序列
cat /root/policy-pipeline-state/last_sync_run.json | head -3
```
飞书静默 = 健康。

## 4. 已知边界(评审定论,接线时心里有数)

- **l2_queue 无锁读改写**:并发安全完全靠本文 flock 串行化;绕过 cron 手跑生产命令时**必须**也拿锁(`flock /var/lock/policy-pipeline-producer.lock <cmd>`)。队列级 fcntl 锁 + 原子写是 W2 前的可选加固。
- **vault↔ledger 对账 sweep 未建**:channel 崩溃窗口(入库后、入队前)的残余缺口,靠每 channel 即时入队已收窄到单 channel;周度对账(vault pids − ledger pids → 补队)留 W2+。
- **drain 对 missing-raw pid 已防卡死**(出队 + StageResult error),失败项看 run_l2 输出的 failed 计数。
- **死信 sweep 状态文件**:`l2_sweep_history.json` 记录每个 pid 已回队次数;`l2_failures.archived.jsonl` 保存已处理死信,放弃项永留归档,供人工追查。
- **文件名控制字符缺口**:sanitize 未滤 \x00-\x1f,若标题携带会让 produce_and_push 的 quotepath 处理失效(概率极低);出现即修 sanitize 正则。
- **重复 pid 双文件 wart**(同 pid 重入库产生 `__1` 同 id 文件)= 既有行为,S3 cleanup 项。
- run_incremental 容器路径拓扑:运行时 state(队列/ledger)在 `/state`,仓内 state(catalog/staging)在 `/app/state`(compose 挂载,见 docker-compose.server.yml policy-producer 注释)。
- **③关系增量三状态文件**:`relations_pid_ledger.json` 记录已覆盖 pid 集;`sem_accepted_cumulative.jsonl` 是累积语义 accepted(部署时由 `state/node3c/sem_accepted_20260606_seed.jsonl` 初始化);`relations_judged_ledger.jsonl` 是 append-only 判定账本,用于防重判。若需全量重判兜底,手动清这三件再跑;这会回到约 1019 对量级的昂贵判定,必须人工决策。
