# Codex 交接:pipeline 代码并入 safety-platform monorepo

> 设计 spec:`docs/superpowers/specs/2026-06-15-pipeline-into-safety-platform-monorepo-design.md`(先读)。
> 运维现状真相源:`docs/runbooks/s2-vps-cron.md`。

**触发 / 背景**:公司决策——把 pipeline **代码** 并入公司 GitLab monorepo `safety-platform` 作 `services/policy-pipeline/`,统一代码库 + 同一 MR/CI 流。数据(vault)早已经 `run_sync` 投影进 `heng-pg`,平台在消费;本次**只搬代码,不动数据同步**。

**已敲定决策(不要重新讨论)**:① 代码进 `services/policy-pipeline/`;② vault 维持独立数据仓 `ZaynShao/energy-policy-analysis`,只读消费,**git 同步机制原样不变**;③ 干净拷贝(不带 git 史)+ 旧仓归档;④ 只带运维文档(SCHEMA/OPERATIONS/runbooks/README),工作笔记(handoffs/superpowers/BACKLOG/LESSONS/CHANGELOG)留旧仓;⑤ 用户已有 monorepo 写/MR 权限。

**成功标准**:MR 合 + GitLab CI 绿 → VPS 从子目录 build → 一次端到端 cron tick 跑通(L1→L2→vault push→投影→heng-guan 见数据)→ vault 同步无回归 → heng-pg 行数对账无掉。

---

## 分工边界(务必分清)

| 谁 | 做什么 |
|---|---|
| **Codex(可直接做)** | Phase A 全部:在 monorepo **独立 fresh clone**(`$SP`,不碰用户在制 clone)准备 `services/policy-pipeline/` 内容、改 compose 卷路径、补 OPERATIONS、落 CI、本地 pytest + docker build 验证、push 分支、开 **GitHub PR**(base `master`)。Phase C 的 README 指针 commit。 |
| **用户亲手(server-ops 红线)** | Phase B 全部:VPS `git pull` + build + **crontab 切换** + 监督首跑 + 对账。GitHub 仓归档(UI)。**Codex 给出逐条命令,用户执行,不替跑。** |

凭据(vault 写 key / LLM key / heng-pg / GitLab key)**绝不打印、不入 git**。

## 纪律(红线)

- **不改 pipeline 业务逻辑**:本次是搬运 + 路径/CI 接线,**零代码行为变化**。代码用 `git ls-files` 原样拷,不顺手重构。
- **不写生产 vault / 不碰 `0_raw/`**。
- **GitHub PR**:Codex push 分支 + 开 **GitHub PR**(base `master`),CODEOWNERS review,合并由用户/owner 决定(进的是公司镜像仓,真 CI 在 DiDi GitLab)。
- 失败回滚锚保留:`/root/policy-pipeline-src` 不删。

---

## Phase A · 代码落仓 + 开 PR(Codex,在 monorepo **独立 fresh clone**)

> **monorepo 现实(实测 2026-06-15)**:canonical 在 DiDi GitLab `git.xiaojukeji.com/gloriahao/safety-platform`;GitHub `gloriahao0909/safety-platform` 是镜像 / PR 协作面。**CI = GitLab `.gitlab-ci.yml`**(validate commit-message+边界 / lint / build / deploy)→ 本 handoff 的 **GitLab 格式 CI job 是对的**。**PR 走 GitHub `gh`**(已 authed ZaynShao),**默认分支 `master`**,有 **CODEOWNERS + PULL_REQUEST_TEMPLATE.md** 要遵守;commit message 受 `validate:commit-message` 卡 → 用 conventional 风格(`feat(policy-pipeline): …`)。
> **⚠️ 用户的本地 clone `~/Documents/战略大盘/safety-platform` 此刻 checkout 在在制 `codex/*` 分支上——绝不在那个 clone 里切分支 / pull / 改文件。Phase A 全程在独立 fresh clone `$SP` 做,同一 shell 会话。**

源 = pipeline 仓 **干净 main**;目标 = monorepo `services/policy-pipeline/`。

### Task A1:独立检出(pipeline 干净 main + monorepo fresh clone off master)

- [ ] **Step 1**:取 pipeline 干净 main 到临时 worktree(不扰用户工作树)

```bash
git -C /Users/shaoziyuan/dev/政策分析-pipeline fetch origin
git -C /Users/shaoziyuan/dev/政策分析-pipeline worktree add /tmp/pp-main origin/main
```
预期:`/tmp/pp-main` 是 main HEAD 干净检出。

- [ ] **Step 2**:monorepo **fresh clone** 到 `$SP`,从干净 `master` 起特性分支(不碰用户在制 clone)

```bash
export SP=/tmp/sp-policy-pipeline
git clone https://github.com/gloriahao0909/safety-platform.git "$SP"
cd "$SP" && git checkout master
git checkout -b feat/add-policy-pipeline-service
```
预期:`$SP` 是干净 `master` 上的新分支;用户的 clone 不受影响。

### Task A2:干净拷贝 tracked 文件(过滤工作笔记)

`git ls-files` 只列**已跟踪**文件 → 自动排除运行时产物、保留 git-tracked 的 `channel_catalog.yaml`/`city_priority.yaml`。再 grep 掉工作笔记前缀。

- [ ] **Step 1**:生成 keep-list

```bash
cd /tmp/pp-main
git ls-files | grep -vE '^(docs/handoffs/|docs/superpowers/|docs/BACKLOG\.md|LESSONS\.md|CHANGELOG\.md|CLAUDE\.md|AGENTS\.md|\.claude/|\.superpowers/|\.DS_Store|.*/\.DS_Store)$' > /tmp/keep.txt
wc -l /tmp/keep.txt   # 预期 ≈ 640(总 653 减掉 ~13 工作笔记文件)
```

- [ ] **Step 2**:拷进 service 目录(保目录结构)

```bash
DST="$SP"/services/policy-pipeline
mkdir -p "$DST"
rsync -a --files-from=/tmp/keep.txt /tmp/pp-main/ "$DST/"
```

- [ ] **Step 3**:核对带了该带的、没带不该带的

```bash
cd "$DST"
ls SCHEMA.md OPERATIONS.md README.md Dockerfile constraints.txt pyproject.toml docker-compose.server.yml   # 都在
ls docs/runbooks/ | head                                                                                   # runbooks 在
ls state/T1_channels/channel_catalog.yaml state/T1_channels/city_priority.yaml                             # 配置在
test ! -e CLAUDE.md && test ! -e LESSONS.md && test ! -d docs/handoffs && test ! -d docs/superpowers && echo "工作笔记已排除 OK"
```
预期:前三行存在,末行打印 `工作笔记已排除 OK`。

### Task A3:写服务级 AGENTS.md(替代未带进来的 CLAUDE.md)

- [ ] **Step 1**:写 `services/policy-pipeline/AGENTS.md`

```markdown
# AGENTS.md · policy-pipeline service

本目录是政策分析 pipeline(L1 采集 / L2 派生 / vault→heng-pg 投影),是 safety-platform 的一个 service。
monorepo 级规则以仓根 `AGENTS.md` / `CLAUDE.md` 为准;本文件只列服务自有约定。

## 必读
- `SCHEMA.md` — vault 数据契约。本服务是生产者,持有 **canonical**;vault 仓(`energy-policy-analysis`)留镜像副本,改 SCHEMA 走 MR 时同步那份。
- `OPERATIONS.md` — 运营手册:cron 接线 / 部署 / 更新 / 回滚。
- `docs/runbooks/`(尤其 `s2-vps-cron.md`)— 部署照抄文本 + 验证命令。

## 红线
- **vault 是独立数据仓,不在本仓**:本服务读写的 vault 经 host 卷挂载(`/root/policy-vault`),raw 只增不删。
- **凭据全 env/CLI,零硬编码,绝不入 git**(vault 写 key / LLM key / heng-pg 凭据)。
- 改动走 **TDD**:新功能 / bugfix 先写失败测试(`tests/`,**mock 网络**,不打真网)再实现。
- **部署 / 生产写是 server-ops 红线,须 operator 亲手。**

## 测试
`pytest -q`(testpaths=tests)。
```

### Task A4:改 compose 卷路径(channel_catalog 易漏点)

- [ ] **Step 1**:把 `policy-producer` 的 `/app/state` 源路径从旧 clone 改到 monorepo 子目录

`services/policy-pipeline/docker-compose.server.yml` 中:
```
旧:  - /root/policy-pipeline-src/state:/app/state # 仓内 state:channel_catalog...
新:  - /root/safety-platform/services/policy-pipeline/state:/app/state # 仓内 state:channel_catalog...
```
(只改这一行;`/root/policy-vault`、`/root/policy-pipeline-state` 两行**不动**——它们不绑代码 checkout。`build: .` 不动——相对 compose 所在目录。)

- [ ] **Step 2**:校验 compose 语法

```bash
cd "$SP"/services/policy-pipeline
docker compose -f docker-compose.server.yml config -q && echo "compose OK"
```
预期:`compose OK`(net `safety-platform_platform-net` external 报缺可忽略——仅本地无该网络,VPS 上有)。

### Task A5:OPERATIONS.md 补部署节(随服务进仓)

- [ ] **Step 1**:在 `services/policy-pipeline/OPERATIONS.md` 末尾追加

```markdown
### 搬入 safety-platform monorepo 后的部署/更新/回滚(2026-06-15)

代码自 2026-06 起住 `safety-platform/services/policy-pipeline/`(公司 GitLab monorepo),不再是独立 `policy-analysis-pipeline` 仓(后者归档作历史锚)。

- **VPS 源路径**:`/root/safety-platform/services/policy-pipeline/`(复用平台已 clone 的 monorepo)。`/root/policy-pipeline-src`(旧独立 clone)保留作回滚锚,稳定后清。
- **更新代码**:`cd /root/safety-platform && git pull && cd services/policy-pipeline && docker compose -f docker-compose.server.yml build`
- **vault 同步不变**:走 vault 仓自己的 git(produce_and_push 推 GitHub vault 仓 / sync_tick 拉回 / run_sync 投影 heng-pg)。凭据双平面:代码 pull=GitLab read(复用平台);vault push=GitHub 写 key 不变。
- **回滚**:crontab 路径 + compose `/app/state` 卷路径切回 `/root/policy-pipeline-src`(`crontab /tmp/cron.bak`),回滚锚保留期内。
```

### Task A6:本地验证(不破坏 = 测试照绿 + 镜像照 build)

- [ ] **Step 1**:venv 跑 pipeline 既有测试(证明拷过来逻辑没断)

```bash
cd "$SP"/services/policy-pipeline
python3 -m venv /tmp/pp-venv && . /tmp/pp-venv/bin/activate   # 任意 3.9+ 即可(pyproject requires-python>=3.9)
grep -vE '^-e ' constraints.txt > /tmp/c.pip
pip install -q -c /tmp/c.pip pyyaml "anthropic>=0.40" "psycopg2-binary>=2.9" trafilatura beautifulsoup4 requests pytest
pip install -q --no-deps -e .
pytest -q
deactivate
```
预期:全绿,通过数与 pipeline 仓一致(网络全 mock,无真网)。

- [ ] **Step 2**:docker build 从新 context(证明 Dockerfile + COPY 在新位置成立)

```bash
cd "$SP"/services/policy-pipeline
docker build -t policy-pipeline:movetest . && echo "build OK"
docker run --rm policy-pipeline:movetest python -c "import trafilatura, bs4; print('imports OK')"
docker rmi policy-pipeline:movetest
```
预期:`build OK` + `imports OK`。

### Task A7:落地 CI(子文件 + 主文件 include · 平台已默认接受)

接法已定(用户拍:默认平台接受推进):pipeline 自维护一个子 CI 文件,主 `.gitlab-ci.yml` 加一行 `include`,**不并进 uv**,默认 shared runner(无 tag)。

- [ ] **Step 1**:写 `services/policy-pipeline/.gitlab-ci.yml`

```yaml
policy-pipeline:test:
  image: python:3.12-slim
  rules:
    - changes: [ "services/policy-pipeline/**/*" ]
  before_script:
    - cd services/policy-pipeline
    - grep -vE '^-e ' constraints.txt > /tmp/c.pip
    - pip install -c /tmp/c.pip pyyaml "anthropic>=0.40" "psycopg2-binary>=2.9" trafilatura beautifulsoup4 requests pytest
    - pip install --no-deps -e .
  script:
    - pytest -q
```

- [ ] **Step 2**:主 `.gitlab-ci.yml` 顶部 `include:` 加一项(无 `include:` 块就新建)

```yaml
include:
  - local: services/policy-pipeline/.gitlab-ci.yml
```

- [ ] **Step 3**:核对改动面

```bash
cd "$SP"
git diff --stat   # 应见 services/policy-pipeline/.gitlab-ci.yml 新增 + .gitlab-ci.yml 改一行
```
(若平台后续给指定 runner tag,在子文件 job 里加 `tags: [<串>]`;默认 shared runner 不加。)

### Task A8:commit + push + 开 PR(GitHub)

先看仓内规范:`cat "$SP"/.github/PULL_REQUEST_TEMPLATE.md "$SP"/.github/CODEOWNERS`,PR 正文按模板填、reviewer 按 CODEOWNERS。commit message 用 conventional(过 `validate:commit-message` 卡)。

- [ ] **Step 1**:commit

```bash
cd "$SP"
git add services/policy-pipeline .gitlab-ci.yml
git commit -m "feat(policy-pipeline): 政策分析 pipeline 作为 service 并入(代码搬运,零行为变化)"
```

- [ ] **Step 2**:push + 开 GitHub PR(base `master`;gh 已 authed ZaynShao)

```bash
git push -u origin feat/add-policy-pipeline-service
gh pr create --repo gloriahao0909/safety-platform --base master --head feat/add-policy-pipeline-service \
  --title "feat: add policy-pipeline service" \
  --body "政策分析 pipeline 代码并入 services/policy-pipeline/。干净拷贝,零行为变化。vault 维持独立数据仓不进仓。CI:子文件 services/policy-pipeline/.gitlab-ci.yml + 主文件 include,独立 pytest job。按 PR 模板补充边界说明。"
```
若 push 报无权限(非协作者)→ 改 fork 流:`gh repo fork gloriahao0909/safety-platform --remote` 后 push 到 fork、`gh pr create` 跨仓。CI(GitLab 镜像侧)绿后由用户/CODEOWNERS 合(平台已默认接受)。

- [ ] **Step 3**:清理临时检出

```bash
git -C /Users/shaoziyuan/dev/政策分析-pipeline worktree remove /tmp/pp-main
rm -rf /tmp/sp-policy-pipeline   # fresh clone,合并后可删
```

**→ Claude 审 PR diff;CODEOWNERS review + 合。合并后进 Phase B。**

---

## Phase B · VPS cutover(用户亲手 · server-ops 红线 · Codex 给命令不替跑)

**前置**:Phase A 的 PR 已合进 monorepo `master`(VPS `/root/safety-platform` 能 pull 到)。

### Task B1:记录搬前基线(heng-pg 行数,用于对账)

```bash
cd /root/safety-platform/services/policy-pipeline   # 注:此时尚是旧 cron 在跑;本步只读
docker compose -f docker-compose.server.yml run --rm policy-pipeline \
  python -c "import os,psycopg2;c=psycopg2.connect(os.environ['DATABASE_URL']);cur=c.cursor();[cur.execute(q) or print(q.split()[-1], cur.fetchone()[0]) for q in ['select count(*) from \"Policy\"','select count(*) from \"PolicyRelation\"']]"
```
记下两数(表名以实际 schema 为准,见 service-deploy plan;若表名不同照改)。

### Task B2:monorepo pull + build + smoke

```bash
cd /root/safety-platform && git pull
cd /root/safety-platform/services/policy-pipeline
ls state/T1_channels/channel_catalog.yaml          # 配置随 MR 到位
docker compose -f docker-compose.server.yml build
docker run --rm policy-pipeline:latest python -c "import trafilatura, bs4; print('OK')"
```
预期:catalog 在、build 成、`OK`。

### Task B3:crontab 切换(备份 → sed → 校验)

cron 里 `/root/policy-pipeline-src` 只作 `cd` 前缀出现;sed 不会误伤 `/root/policy-pipeline-state`(不同串)或 `/root/policy-vault`。

```bash
crontab -l > /tmp/cron.bak                          # 备份(回滚锚)
crontab -l | sed 's#/root/policy-pipeline-src#/root/safety-platform/services/policy-pipeline#g' > /tmp/cron.new
diff /tmp/cron.bak /tmp/cron.new                    # 人眼核:只动 cd 前缀,行数不变
crontab /tmp/cron.new
crontab -l | grep -c policy-pipeline                # 确认装上
```
**回滚**:`crontab /tmp/cron.bak`。

### Task B4:监督首跑 + 四验证(对照 s2-vps-cron.md §2)

人在场手跑一条写 vault 的 cron 等价命令(持 flock),如 07:30 评论 ingest:

```bash
set -a; . /etc/policy-pipeline/notify.env; . /etc/policy-pipeline/commentary.env; set +a
cd /root/safety-platform/services/policy-pipeline
flock -w 7200 /var/lock/policy-pipeline-producer.lock \
  docker compose -f docker-compose.server.yml run --rm -e WEWE_FEED_URL -e WEWE_AUTH_CODE \
  policy-producer python -m scripts.l1_collect.commentary_ingest.run \
  --feed-url "$WEWE_FEED_URL" --auth-code "$WEWE_AUTH_CODE" \
  --vault-dir /vault --state-dir /state --since 2026-06-06 --feed-timeout 600
/usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
  --whitelist 0_raw/commentaries/ --message "l1(commentary): post-move supervised run"
# 投影:
flock -w 7200 /var/lock/policy-pipeline-producer.lock \
  docker compose -f docker-compose.server.yml run --rm policy-pipeline \
  python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1
```

验证四件:
1. `git -C /root/policy-vault log -1` 有该 commit 且 `status` 干净;
2. GitHub `origin/main` 同 HEAD(`git -C /root/policy-vault log origin/main -1`);
3. `cat /root/policy-pipeline-state/last_sync_run.json` `errors=[]`;
4. heng-pg 行数 ≥ B1 基线(无掉);飞书无告警。

**全过 → 观察次日自动 cron 一轮(`tail -5 /var/log/policy-pipeline/ingest.log`,飞书静默=健康)。**

---

## Phase C · 旧仓归档(Phase B 稳定后)

- [ ] **Codex**:在 pipeline 仓 `README.md` 顶部加指针 commit(走正常 PR 到该仓 main):
  > ⚠️ 代码已迁入公司 monorepo `safety-platform/services/policy-pipeline/`(2026-06)。本仓为**历史归档 + 工作笔记**(docs/handoffs、docs/superpowers、BACKLOG、LESSONS)存档,不再接收功能改动。
- [ ] **用户亲手**:GitHub `ZaynShao/policy-analysis-pipeline` → Settings → Archive(只读)。

---

## 平台对齐(用户拍 2026-06-15:默认平台接受,推进 —— 不阻塞)

已按"默认接受"定死,无需等回复:
1. 落位 `services/policy-pipeline/` + 服务自包含(pip+constraints,不并 root uv)—— 照做。
2. CI:子文件 `services/policy-pipeline/.gitlab-ci.yml` + 主文件 `include`,独立 pytest job —— 已在 Task A7 落地。**CI 实跑在 DiDi GitLab(`.gitlab-ci.yml` 是真 CI),GitHub 侧是 PR 协作面**;GitLab 格式正确。runner 默认随仓既有约定,平台若给指定 tag 再在子文件 job 加 `tags:`。
3. 合并:GitHub PR,CODEOWNERS review,CI 绿后用户/owner 点合;commit message + 边界过 `validate` 阶段。
4. VPS `git pull` + cron 路径切换:cutover 前给平台**报备一声**(FF 安全,不动其服务 / root compose),非阻塞。
> 若平台事后提异议(如指定 runner tag / 换落位),回到对应 Task 局部调整即可,不影响整体路径。

## 回滚总览

| 阶段 | 回滚 |
|---|---|
| Phase A | PR 不合即可,无副作用;fresh clone `/tmp/sp-policy-pipeline` 删掉 |
| Phase B | `crontab /tmp/cron.bak` + 源路径切回 `/root/policy-pipeline-src`(回滚锚在) |
| Phase C | 归档可解除;README 指针 revert |
