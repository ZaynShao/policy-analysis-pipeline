# Stage 1 持续上云管道 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).
> **本项目分工**:Task 1 = Codex 写码(TDD);Task 2-5 = 服务器 ops(Claude 驱动 SSH + 用户确认破坏性步);Task 6 = 文档。每个 task 标了执行人。
> **spec**:`docs/superpowers/specs/2026-06-08-stage1-continuous-sync-design.md`

**Goal:** producer 产出的 vault 经 git 持续、自动、可靠地投影到云端 heng-pg,告别手动 rsync + 手动 run_sync。

**Architecture:** producer commit+push vault → GitHub(vault 仓)→ Tokyo host cron 每天 1 次 `git pull`(变了才拉)→ 容器 `run_sync` 读 vault 写 heng-pg。本 stage 生成仍在 producer 本地;服务器只读消费;先 staging,cutover 后指生产。

**Tech Stack:** git(浅克隆)、docker compose、host cron、Python 3.9+(sync_tick 决策核 + pytest)、psycopg2(run_sync 已有)。

---

## File Structure

- `scripts/service/sync_tick.py`(新,pipeline 仓)— 决策核(`should_sync` / `build_run_sync_cmd`,纯函数可测)+ `main()`(host 侧 git fetch/rev-parse/reset + 调 run_sync,subprocess 编排)。
- `tests/service/test_sync_tick.py`(新)— 决策核单测。
- 服务器(无仓内文件):deploy key、`/root/policy-vault` 切 git、cron entry、logrotate。
- `OPERATIONS.md`(改)— 补 Stage 1 运维节。

---

## Task 1: sync_tick 决策核 + 编排(Codex · TDD)

**Files:**
- Create: `scripts/service/sync_tick.py`
- Test: `tests/service/test_sync_tick.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/service/test_sync_tick.py
from scripts.service.sync_tick import should_sync, build_run_sync_cmd


def test_should_sync_true_when_shas_differ():
    assert should_sync("aaa", "bbb") is True


def test_should_sync_false_when_shas_equal():
    assert should_sync("aaa", "aaa") is False
    assert should_sync(" aaa\n", "aaa") is False  # 容错空白


def test_should_sync_false_when_either_empty():
    assert should_sync("", "bbb") is False
    assert should_sync("aaa", "") is False


def test_build_run_sync_cmd_shape():
    cmd = build_run_sync_cmd(
        compose_file="docker-compose.server.yml",
        vault="/vault", state="/state", version=1,
    )
    assert cmd[:6] == ["docker", "compose", "-f", "docker-compose.server.yml", "run", "--rm"]
    assert "policy-pipeline" in cmd
    assert cmd[-6:] == ["-m", "scripts.sync.run_sync", "--vault", "/vault", "--state-dir", "/state"] or \
        ("--vault" in cmd and "/vault" in cmd and "--pipeline-version" in cmd and "1" in cmd)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/service/test_sync_tick.py -v`
Expected: FAIL,`ModuleNotFoundError: ... sync_tick`

- [ ] **Step 3: 实现 sync_tick.py**

```python
# scripts/service/sync_tick.py
"""Stage 1 持续上云 tick(host 侧,cron 调度)。

git fetch vault → 远端 HEAD 变了才 reset 到最新 → docker compose run run_sync。
git/docker 经 subprocess;决策核(should_sync/build_run_sync_cmd)纯函数可测。
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def should_sync(local_sha: str, remote_sha: str) -> bool:
    """本地与远端 HEAD 都非空且不同 → 需同步。"""
    l, r = (local_sha or "").strip(), (remote_sha or "").strip()
    return bool(l) and bool(r) and l != r


def build_run_sync_cmd(*, compose_file: str, vault: str, state: str, version: int) -> list:
    """构造容器内跑 run_sync 的命令(便于测试/复用)。"""
    return [
        "docker", "compose", "-f", compose_file, "run", "--rm", "policy-pipeline",
        "python", "-m", "scripts.sync.run_sync",
        "--vault", vault, "--state-dir", state, "--pipeline-version", str(version),
    ]


def _git(args: list, cwd: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault-dir", required=True)        # host 上 vault git 目录,如 /root/policy-vault
    ap.add_argument("--pipeline-dir", required=True)     # host 上 pipeline 仓目录,如 /root/policy-pipeline(docker compose run 的 cwd)
    ap.add_argument("--compose-file", required=True)     # 如 /root/policy-pipeline/docker-compose.server.yml
    ap.add_argument("--container-vault", default="/vault")
    ap.add_argument("--container-state", default="/state")
    ap.add_argument("--pipeline-version", type=int, default=1)
    ap.add_argument("--branch", default="main")
    args = ap.parse_args(argv)

    ts = datetime.now(CST).isoformat(timespec="seconds")
    try:
        _git(["fetch", "--depth=1", "origin", args.branch], args.vault_dir)
        local = _git(["rev-parse", "HEAD"], args.vault_dir)
        remote = _git(["rev-parse", f"origin/{args.branch}"], args.vault_dir)
    except subprocess.CalledProcessError as e:
        print(f"[{ts}] git error: {e.stderr or e}", file=sys.stderr)
        return 2

    if not should_sync(local, remote):
        print(f"[{ts}] no change (HEAD={local[:8]}), skip sync")
        return 0

    _git(["reset", "--hard", f"origin/{args.branch}"], args.vault_dir)
    print(f"[{ts}] vault {local[:8]} -> {remote[:8]}, running run_sync")
    cmd = build_run_sync_cmd(
        compose_file=args.compose_file,
        vault=args.container_vault, state=args.container_state,
        version=args.pipeline_version,
    )
    proc = subprocess.run(cmd, cwd=args.pipeline_dir)
    print(f"[{ts}] run_sync exit={proc.returncode}")
    return proc.returncode
```

> 说明:`main()` 的 git/docker 走真实进程,不在单测覆盖(集成在 Task 5 staging 验);单测只盖 `should_sync`/`build_run_sync_cmd` 决策核。失败告警在 Task 5 接(过渡期 stderr + run_sync 的 last_sync_run.json;正式接消息 = 配套消息 plan)。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/service/test_sync_tick.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: principle_guard + 提交**

Run: `python3 -m scripts.audit.principle_guard scripts/service`(应 clean)
```bash
git add scripts/service/sync_tick.py tests/service/test_sync_tick.py
git commit -m "feat(service): sync_tick — git pull vault(变了才拉)+ 调 run_sync[Stage1]"
```

---

## Task 2: 服务器 deploy key(Claude ops · 用户授权)

**目的**:服务器只读拉 vault 仓,私钥本地、不入仓。

- [ ] **Step 1**:服务器生成专用 key
```bash
ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173 \
  'ssh-keygen -t ed25519 -f ~/.ssh/vault_deploy -N "" -C "tokyo-vault-readonly" && cat ~/.ssh/vault_deploy.pub'
```
- [ ] **Step 2**:把输出的公钥加到 GitHub `ZaynShao/energy-policy-analysis` → Settings → Deploy keys(**read-only,不勾 write**)。(用户在 GitHub 操作。)
- [ ] **Step 3**:服务器 git 用该 key
```bash
ssh -i <pem> root@8.216.59.173 'cat >> ~/.ssh/config <<EOF
Host github-vault
  HostName github.com
  User git
  IdentityFile ~/.ssh/vault_deploy
  IdentitiesOnly yes
EOF'
```
- [ ] **Step 4 验证**:`ssh -i <pem> root@<srv> 'ssh -T git@github-vault'` → 见 "Hi ZaynShao/energy-policy-analysis ... read-only access"。

---

## Task 3: /root/policy-vault rsync→git 切换(Claude ops · ⚠️破坏性 · 用户确认)

**⚠️ 这步删/换现有 rsync 目录,执行前用户确认。**

- [ ] **Step 1 备份现目录**
```bash
ssh -i <pem> root@<srv> 'mv /root/policy-vault /root/policy-vault.rsync-bak-$(date +%s)'
```
- [ ] **Step 2 浅克隆**
```bash
ssh -i <pem> root@<srv> 'git clone --depth=1 git@github-vault:ZaynShao/energy-policy-analysis.git /root/policy-vault'
```
- [ ] **Step 3 验证**:`ls /root/policy-vault/0_raw/policies | wc -l`(应 ~1032)+ `git -C /root/policy-vault rev-parse --short HEAD`。
- [ ] **Step 4**:确认无误后删备份(或留几天):`# rm -rf /root/policy-vault.rsync-bak-*`。
- [ ] **回滚锚**:出问题 → `rm -rf /root/policy-vault && mv /root/policy-vault.rsync-bak-* /root/policy-vault`。

---

## Task 4: host cron + logrotate(Claude ops)

- [ ] **Step 1**:确保服务器有 pipeline 仓(跑 sync_tick.py 需要)+ 镜像(Task 1 提交后拉/重建)。`cd /root/policy-pipeline && git pull`(或首次 clone)。
- [ ] **Step 2**:cron entry(每天 21:00,producer 当天产完后)
```bash
ssh -i <pem> root@<srv> '(crontab -l 2>/dev/null; echo "0 21 * * * cd /root/policy-pipeline && /usr/bin/python3 -m scripts.service.sync_tick --vault-dir /root/policy-vault --pipeline-dir /root/policy-pipeline --compose-file /root/policy-pipeline/docker-compose.server.yml >> /var/log/policy-pipeline/sync_tick.log 2>&1") | crontab -'
ssh -i <pem> root@<srv> 'mkdir -p /var/log/policy-pipeline'
```
- [ ] **Step 3**:logrotate
```bash
ssh -i <pem> root@<srv> 'cat > /etc/logrotate.d/policy-pipeline <<EOF
/var/log/policy-pipeline/*.log { weekly rotate 4 compress missingok notifempty }
EOF'
```
- [ ] **Step 4 验证**:`crontab -l` 含该行;手动跑一次见下 Task 5。

---

## Task 5: 集成验证(staging)(Claude ops)

前提:`pipeline.env` 的 `DATABASE_URL` 指 **staging**(`hengguan_staging`)。

- [ ] **Step 1 无变更跳过**:`ssh ... 'cd /root/policy-pipeline && python3 -m scripts.service.sync_tick --vault-dir /root/policy-vault --pipeline-dir /root/policy-pipeline --compose-file /root/policy-pipeline/docker-compose.server.yml'` → 日志 "no change, skip"(因刚 clone,HEAD=远端)。
- [ ] **Step 2 有变更同步**:producer 端 push 一个小 vault 变更(改一篇 bv 或加一关系)→ 服务器再跑 sync_tick → 日志 "vault X->Y, running run_sync" + exit=0 → 查 staging DB 反映该变更 + `last_sync_run.json` errors 空。
- [ ] **Step 3 失败信号**:临时把 `pipeline.env` 的 `DATABASE_URL` 改坏 → 跑 sync_tick → run_sync exit≠0 + last_sync_run errors 非空 + 日志可见(过渡期);恢复 env。
- [ ] **Step 4**:等一个真实 cron 周期(或确认 cron 行无误),确认自动跑通。

---

## Task 6: OPERATIONS.md(Claude · 文档)

- [ ] 在 `OPERATIONS.md` 加 "Stage 1 持续上云" 节:架构一图、sync_tick 用法、cron 行、rsync→git 切换 + 回滚、staging→生产 cutover 指针(DATABASE_URL 切换)。提交。

---

## Self-Review

- **Spec 覆盖**:C0 git 传输=Task 2/3;cron+sync_tick=Task 1/4;run_sync 串接=Task 1 main;失败可见=Task 5(过渡)+ 消息 plan(正式);staging→生产=Task 5 前提 + Task 6 指针。✅ 全覆盖。
- **占位扫描**:无 TBD;命令/代码均具体。`<pem>`/`<srv>` 是明确占位符(`~/.ssh/aliyun-tokyo-20260606.pem` / `root@8.216.59.173`),首次执行时替实。
- **类型一致**:`should_sync`/`build_run_sync_cmd` 在测试与实现签名一致;cron 调的参数名(`--vault-dir`/`--compose-file`)与 argparse 一致。
- **缺口**:正式失败告警依赖配套"消息 plan"(并行);本 plan 过渡期用 stderr+last_sync_run.json,不阻塞。
