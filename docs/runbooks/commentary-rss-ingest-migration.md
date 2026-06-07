# 评论 RSS 入库 · Mac→国内容器 迁移 runbook

## 现状(阶段一,Mac)
- wewe-rss:`docker run ... cooderl/wewe-rss-sqlite:latest`(端口 4000,数据卷 ~/wewe-rss-data)
- ingest:`python3 -m scripts.l1_collect.commentary_ingest.run`,Mac cron 定时
- 写 Mac vault 0_raw/commentaries/,经现有 Mac→东京 rsync 上服务器只读消费

## 为什么国内(不上东京服务器)
token 是个人微信读书账号;东京机房 IP 触发微信地理风控(最坏冻结账号)。详见 spec §6.1。
**国内容器节点同理:token 必须从国内 IP 发起。**

## 迁移步骤(定下国内容器节点后)
1. 国内节点装 Docker;`docker/wewe-rss/compose.yml` 起 wewe-rss,挂持久盘。
2. 把 Mac 的 `~/wewe-rss-data/wewe-rss.db` scp 到节点 `./data/`(保留已登录 token,免重扫)。
   - 若 token 已失效:开 4000 管理页,手机微信扫码重登(见"扫码")。
3. 配 `.env`:`WEWE_AUTH_CODE` / `ALERT_WEBHOOK_URL`(不入 git)。
4. ingest 接入(二选一):
   - a) 节点 cron:`cd <repo> && VAULT_DIR=<vault> WEWE_FEED_URL='http://wewe-rss:4000/feeds/all.json?limit=400' WEWE_AUTH_CODE=... python3 -m scripts.l1_collect.commentary_ingest.run --db-path <db>`
   - b) ingest 也容器化,与 wewe-rss 同 compose 网络,feed-url 用服务名 `http://wewe-rss:4000/feeds/all.json?limit=400`

   > **feed limit 纪律(重要,别被限住)**:wewe-rss **不带 `limit` 默认只回 30 条/次**(实测)。15 个号合并、忙时 6h 内发文常 >30 → 会**静默漏**。务必显式给**大 limit**(如 400;wewe-rss 留全量历史,大 limit 只是多扫被去重,代价极小)。代码侧**不硬编码 limit**,完全由 `WEWE_FEED_URL` 控制;`coverage_warning`(本轮与已见零重叠)是兜底信号,出现就调大 limit / 提频。
5. vault 落地与回流:节点写本地 vault 副本 → 约定回流路径(rsync 回 Mac 或直接作为新的 vault 著作点,二选一,迁移时定并更新 spec §9 + 本 runbook)。
6. 验证:`--check-token` 通;小批量 `--no-fallback` 干跑;过 `validate_schema`。

## 扫码(token 失效时)
1. 浏览器开节点 `http://<节点>:4000`(或反代),输入 AUTH_CODE 进管理页。
2. 账号管理 → 扫码登录 → 手机微信扫 → token 刷新。
3. （后续)openclaw + IM 模块:自动把 QR 推到 IM,远程扫——独立 spec,届时接 `--check-token` 告警为触发点。

## 保守轮询纪律
轮询越勤 → token 废越快 → 扫码越频繁(且抬高封号风险)。`CRON_EXPRESSION` 维持 6h/次量级,勿调激进。
