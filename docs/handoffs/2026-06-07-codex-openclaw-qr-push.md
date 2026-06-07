# Codex 交接:openclaw「二维码失效」推送模块

**目标**:wewe-rss 微信读书 token 失效时,**自动把重新登录的二维码推到 IM**,用户远程扫一下即可恢复采集——消灭"人盯着、手动开页面扫码"的运维负担。

**分支纪律**:新开你自己的分支,**不要碰** `feat/service-deploy`、`claude/zen-saha-c3ac3c`(本评论入库线)、`state/node3c/`。只新增,不改本线已有文件(可调用其接口)。

**部署位置**:**国内节点**(先 Mac,后续国内容器)。token 是个人微信读书账号,东京 IP 会触发微信地理风控——详见 `docs/superpowers/specs/2026-06-07-commentary-rss-ingest-design.md` §6.1。openclaw 也必须跑国内。

---

## 一、已经建好的「检测/告警 seam」(你接在这之上)

本评论入库线(`scripts/l1_collect/commentary_ingest/`)已提供:

| 接口 | 签名 | 作用 |
|---|---|---|
| `token_health.check_token(db_path)` | → `TokenStatus(valid, account_name, detail)` | 读 sqlite `accounts.status`(1=有效/0=失效)判 token 死活 |
| `token_health.alert(message, webhook_url)` | → `bool` | 现有告警通道(webhook POST `{text}`);占位,你可扩展 |
| `run.py --check-token --db-path ...` | exit 0=有效 / 1=失效,并触发 alert | **这就是你的触发点** |

**触发设计**:cron 周期跑 `--check-token`(或入库 run 内已自带检测)→ 失效 → 调你的 openclaw 推送流程。

> 注意一个实测坑:**UI 里把账号 toggle 成"启用"≠ token 真活**。只有真扫码拿到新 token 才有效;wewe-rss 一旦拿失效 token 去用会自动打回 `status=0`。所以恢复成功的判据 = 扫码后 `check_token` 持续 valid(见下轮询)。

---

## 二、wewe-rss 扫码登录全流程(已实测,端点/鉴权/载荷钉死)

wewe-rss 本机容器:`cooderl/wewe-rss-sqlite:latest`(Docker Hub 直连被墙,用 `docker.1ms.run` 镜像源拉),端口 4000,`AUTH_CODE=zayn-policy-2026`,数据卷 `~/wewe-rss-data`。

**两种鉴权头(实测,别搞混)**:
- **feed 端点**(`/feeds/*`):`Authorization: Bearer <AUTH_CODE>`
- **tRPC 管理端点**(`/trpc/*`):`Authorization: <AUTH_CODE>`(**裸 code,无 Bearer**)

**扫码恢复三步(全是 tRPC,无 superjson,响应形如 `{"result":{"data":...}}`)**:

```
① 生成二维码会话
   POST /trpc/platform.createLoginUrl
   Header: Authorization: <AUTH_CODE>
   Body:   {}
   → {"result":{"data":{"uuid":"091Wk1oV1rCMll25",
                        "scanUrl":"https://open.weixin.qq.com/connect/confirm?uuid=091Wk1oV1rCMll25"}}}
   // scanUrl 编成二维码图片 = 用户用微信扫的码

② 把 scanUrl 渲染成 QR 图 → 经 openclaw 推到 IM(见第三节)

③ 轮询扫码结果(用户扫完才成功)
   GET /trpc/platform.getLoginResult?input=<urlencoded {"id":"<uuid>"}>
   Header: Authorization: <AUTH_CODE>
   → 成功后返回登录态;wewe-rss 把新 token 写入 accounts 表、status 置 1
   // tRPC query 的 input 走 url:?input={"json"无transformer时直接{"id":"..."}};
   //   实测无 transformer,form 为 ?input=%7B%22id%22%3A%22<uuid>%22%7D,按需验证一次

④ 确认恢复:token_health.check_token(db_path).valid == True(持续,非瞬时)
```

> QR 渲染:scanUrl 是纯文本 URL,用任意 qrcode 库(Python `qrcode`/`segno`)生成 PNG 即可,无需依赖 wewe-rss 出图。

---

## 三、openclaw 集成点(需你补实)

**我(Claude)不掌握 openclaw 的真实 API**,这块需要你从 openclaw 文档或用户处拿到具体接口。把它抽象成一个 adapter:

```
openclaw_adapter.push_qr(image_path_or_bytes, caption: str, target: str) -> bool
    # 把二维码图 + 文案推到指定 IM 会话;返回是否送达
```

**待用户/你确认的 openclaw 事实**:
- openclaw 连的是哪个 IM(微信/企业微信/Telegram/Slack/飞书…)?
- 推图片的 API 形态(HTTP? SDK? CLI?)+ 鉴权方式
- 目标会话/群标识怎么指定
- openclaw 部署形态(容器?进程?)——须国内节点

**安全**:openclaw 凭据(IM token 等)**绝不进 git**,走 env/凭据文件(对齐本仓 §9 凭据纪律 + 服务器 `/etc/policy-pipeline/pipeline.env` 约定)。

---

## 四、建议模块结构 + done-gate

```
scripts/l1_collect/commentary_ingest/qr_relay/   # 或你认为合适的位置
  detector.py     # 复用 token_health.check_token;失效→触发
  wewe_login.py   # createLoginUrl / 轮询 getLoginResult(封装上面三步)
  qr_render.py    # scanUrl → QR PNG
  openclaw.py     # openclaw adapter(push_qr)
  run.py          # 编排:检测失效→生成QR→推IM→轮询→确认恢复→记日志
```

**done-gate**:
1. 模拟/真实 token 失效 → 自动生成 QR 并推到 IM(用户能在 IM 里看到可扫的码)
2. 用户扫码后,轮询能检出登录成功,`check_token` 转 valid
3. 全程凭据零泄漏(git 无 IM token / AUTH_CODE 真值)
4. 跑国内节点;TDD 覆盖(wewe_login 的 createLoginUrl/poll 用 mock HTTP,qr_render 纯函数,detector 用临时 sqlite)
5. 失败优雅:openclaw 不可达 / 扫码超时 → 退回现有 alert 文案,不崩

---

## 五、可直接拿来测的事实速查

- 本机 wewe-rss 正在跑(容器名 `wewe-rss`,:4000),token 当前 **valid**(刚扫过)
- DB:`~/wewe-rss-data/wewe-rss.db`,表 `accounts(id,name,status,token,...)`;`statusMap: INVALID=0/ENABLE=1/DISABLE=2`
- 触发刷新(验证用):`POST /trpc/feed.refreshArticles` body `{}` header 裸 AUTH_CODE
- 本线 spec/plan:`docs/superpowers/specs/2026-06-07-commentary-rss-ingest-design.md`、`docs/superpowers/plans/2026-06-07-commentary-rss-ingest.md`
