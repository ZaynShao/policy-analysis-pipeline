# S2 · VPS 单生产者全自动编排 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 L1 政策/评论、L2 派生、vault 写权威、DB 投影全部翻到东京 VPS 单机全自动 cron,Mac 退役为只读+热备。

**Architecture:** 六个 TDD 小件(notify / produce_and_push / ingest --since / fetcher proxy-fallback / L1→L2 接线 / route 模块转正)+ compose 加 producer 服务 + host cron 编排;W0–W4 波次上线,每波验证后进下一波。

**Tech Stack:** Python 3.12(容器)/3.14(host 胶水,stdlib+venv)、Docker Compose、git(vault 双写,S1 基座)、openclaw→飞书告警。

**Spec:** `docs/superpowers/specs/2026-06-10-s2-vps-single-producer-design.md`

**纪律红线(全程)**:凭据不进 git/聊天;代理 env 只给 L1 fetch(回归测试);vault raw 只增不删;服务器生产写操作 = 用户 bypass 授权下执行;每任务一 commit。

---

## W0 · 前置(Task 0.x,运维为主)

### Task 0.1: commit 既有修复 + 本计划,合 main

**Files:** 已改未提交:`scripts/l1_collect/commentary_ingest/qr_relay/wewe_login.py`、`qr_relay/run.py`、`tests/commentary_qr_relay/test_wewe_login.py`、`test_run.py`、`pyproject.toml`、spec、本文件。

- [ ] Step 1: 跑全量测试确认绿:`python3 -m pytest tests/ -q`(预期全 pass)
- [ ] Step 2: 三个 commit 分开提:
```bash
git add scripts/l1_collect/commentary_ingest/qr_relay/ tests/commentary_qr_relay/
git commit -m "fix(qr_relay): 扫码成功后显式 account.add 落库(v2.6.1 getLoginResult 只读不写库)"
git add pyproject.toml
git commit -m "feat(deps): 加 trafilatura/beautifulsoup4/requests(commentary ingest 容器依赖)"
git add docs/superpowers/specs/2026-06-10-s2-vps-single-producer-design.md docs/superpowers/plans/2026-06-10-s2-vps-single-producer.md
git commit -m "docs(s2): VPS 单生产者全自动编排 spec + plan"
```
- [ ] Step 3: push 分支 → PR → 合 main(用户在场确认合并)

### Task 0.2: 服务器代码更新 + 镜像构建

- [ ] Step 1: `ssh <vps> 'cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main'`
- [ ] Step 2: `ssh <vps> 'cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml build'`(镜像现缺,首次构建;预期 build 成功、含新依赖)
- [ ] Step 3: 验证:`docker run --rm policy-pipeline:latest python -c "import trafilatura, bs4; print('deps ok')"`

### Task 0.3: 凭据落位(用户亲手,out-of-git)

- [ ] `/etc/policy-pipeline/models.env`(0600):照 Mac 侧同名键迁 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `JUDGE_MODEL` + run_2b 所需 anthropic 系键(+可选 `FIRECRAWL_API_KEY` / `TAVILY_API_KEY`)
- [ ] openclaw 装上 VPS + `/etc/policy-pipeline/notify.env`(0600):`OPENCLAW_CHANNEL` / `OPENCLAW_ACCOUNT` / `OPENCLAW_IM_TARGET` / `OPENCLAW_COMMAND`(值同 Mac `~/.config/policy-pipeline/wewe-qr-relay.env`)
- [ ] `/etc/policy-pipeline/commentary.env`(0600):`WEWE_AUTH_CODE`(同 `/root/wewe-rss/.env`)、`WEWE_FEED_URL=http://wewe-rss:4000/feeds/all.json?limit=400`(**容器视角**,经 platform-net 服务名,见 Task 0.5)、`WEWE_BASE_URL=http://127.0.0.1:4000`(**host 哨兵视角**)、`WEWE_DB_PATH=/root/wewe-rss/data/wewe-rss.db`
- [ ] 验证:`bash -c 'set -a; . /etc/policy-pipeline/notify.env; set +a; "$OPENCLAW_COMMAND" message send --channel "$OPENCLAW_CHANNEL" --account "$OPENCLAW_ACCOUNT" --target "$OPENCLAW_IM_TARGET" --message "[policy-pipeline] VPS notify 通道连通测试" --json'`(飞书收到即通)

### Task 0.4: vault git 身份 + Mac 残留 commit 推送(用户亲手)

- [ ] VPS:`git -C /root/policy-vault config user.name "policy-pipeline-vps" && git -C /root/policy-vault config user.email "pipeline@vps.local"`
- [ ] VPS:确认 vault remote 用可写 key(S1 T1 已配 github-vault-rw;`git -C /root/policy-vault remote -v` 应指 `git@github-vault-rw:...`)
- [ ] Mac:推 2 个残留 vault commit(80332f2f 脏数据清理 + 5ca68df9 文档):`cd ~/Documents/Zayn\ Main/政策分析 && git push origin main`
  (注:删除的 15 条市监脏政策因 upsert-no-prune 在 DB 留孤儿 → 已记 S3,本期不处理)
- [ ] VPS 同步到位:`ssh <vps> 'cd /root/policy-pipeline-src && python3 -m scripts.service.sync_tick --vault-dir /root/policy-vault --pipeline-dir /root/policy-pipeline-src --compose-file /root/policy-pipeline-src/docker-compose.server.yml'`(预期 reset 到新 HEAD + run_sync 投影)

### Task 0.5: wewe-rss 容器加入 platform-net(让 producer 容器够到 feed)

背景:wewe-rss 端口只绑 host `127.0.0.1:4000`(管理页安全),bridge 网络的 producer 容器够不着;`docker compose run` 不支持 `--network` 覆盖。解法:wewe-rss 加入外部网 `safety-platform_platform-net`,producer 经服务名 `http://wewe-rss:4000` 访问;host 侧 127.0.0.1 绑定保留(SSH 隧道/哨兵用)。

- [ ] Step 1: 编辑 `/root/wewe-rss/compose.yml`,在 `services.wewe-rss` 下加:

```yaml
    networks: [platform-net]
```

  文件尾追加:

```yaml
networks:
  platform-net:
    external: true
    name: safety-platform_platform-net
```

- [ ] Step 2: `cd /root/wewe-rss && docker compose up -d`(重建容器,数据卷不受影响)
- [ ] Step 3: 验证容器互通:`docker run --rm --network safety-platform_platform-net curlimages/curl -sS -o /dev/null -w "%{http_code}\n" "http://wewe-rss:4000/feeds/all.json?limit=1"`(预期 200)
- [ ] Step 4: 验证 host 侧仍通:`curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4000/`(预期 200)

---

## 代码件(Task 1–8,全部在本仓,TDD)

### Task 1: scripts/service/notify.py(统一告警 helper)

**Files:**
- Create: `scripts/service/notify.py`
- Test: `tests/service/test_notify.py`

设计:薄封装复用 `OpenClawMessageAdapter.push_text`(DRY);env 缺失/推送失败**绝不 raise**(告警通道不能反过来弄死主流程),返回 bool;CLI 入口给 cron 用。

- [ ] Step 1: 写失败测试:

```python
# tests/service/test_notify.py
from scripts.service import notify


class FakeAdapter:
    def __init__(self):
        self.sent = []

    def push_text(self, message, target):
        self.sent.append((message, target))
        return True


def test_send_text_pushes_via_adapter_with_env_target(monkeypatch):
    monkeypatch.setenv("OPENCLAW_IM_TARGET", "ou_x")
    fake = FakeAdapter()
    ok = notify.send_text("hello", adapter=fake)
    assert ok is True
    assert fake.sent == [("hello", "ou_x")]


def test_send_text_returns_false_when_env_missing(monkeypatch):
    monkeypatch.delenv("OPENCLAW_CHANNEL", raising=False)
    monkeypatch.delenv("OPENCLAW_IM_TARGET", raising=False)
    assert notify.send_text("hello") is False


def test_send_text_never_raises_on_adapter_error(monkeypatch):
    monkeypatch.setenv("OPENCLAW_IM_TARGET", "ou_x")

    class Boom:
        def push_text(self, message, target):
            raise RuntimeError("openclaw down")

    assert notify.send_text("hello", adapter=Boom()) is False
```

- [ ] Step 2: 跑测试确认失败:`python3 -m pytest tests/service/test_notify.py -q`(预期 `ModuleNotFoundError`/属性缺失)
- [ ] Step 3: 最小实现:

```python
# scripts/service/notify.py
"""统一告警:openclaw→飞书文字。绝不 raise(告警通道不得弄死主流程)。

env:OPENCLAW_CHANNEL / OPENCLAW_ACCOUNT / OPENCLAW_IM_TARGET / OPENCLAW_COMMAND
CLI:python3 -m scripts.service.notify "消息"(cron `|| notify` 用,恒 exit 0)
"""
from __future__ import annotations

import os
import sys
from typing import Any


def send_text(message: str, *, adapter: Any | None = None) -> bool:
    target = os.environ.get("OPENCLAW_IM_TARGET", "")
    try:
        if adapter is None:
            channel = os.environ.get("OPENCLAW_CHANNEL", "")
            if not channel or not target:
                return False
            from scripts.l1_collect.commentary_ingest.qr_relay.openclaw import (
                OpenClawMessageAdapter,
            )
            adapter = OpenClawMessageAdapter(
                channel=channel,
                account=os.environ.get("OPENCLAW_ACCOUNT", ""),
                command=os.environ.get("OPENCLAW_COMMAND", "openclaw"),
            )
        if not target:
            return False
        return bool(adapter.push_text(message, target))
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    msg = " ".join(args) or "[policy-pipeline] (空告警)"
    sent = send_text(msg)
    print(f"notify sent={sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] Step 4: 跑测试确认过:`python3 -m pytest tests/service/test_notify.py -q`(预期 3 passed)
- [ ] Step 5: Commit:`git add scripts/service/notify.py tests/service/test_notify.py && git commit -m "feat(service): notify 统一告警 helper(openclaw 文字·绝不 raise)"`

### Task 2: scripts/service/produce_and_push.py(生产后 git 收尾)

**Files:**
- Create: `scripts/service/produce_and_push.py`
- Test: `tests/service/test_produce_and_push.py`

设计:`classify_changes(porcelain, whitelist)` 纯函数 + `run(vault_dir, whitelist, message)` 流程 + CLI。白名单外改动 = 异常(告警、不提交、exit 4);空变更 exit 0;push 失败保留本地 commit(exit 5,下轮 cron 重试,期间 S1 守卫对 local_ahead 会 abort 不会 reset)。git 操作照 `sync_tick._git` 风格(subprocess check=True)。

- [ ] Step 1: 写失败测试:

```python
# tests/service/test_produce_and_push.py
import subprocess
from pathlib import Path

import pytest

from scripts.service.produce_and_push import classify_changes, run


def test_classify_splits_whitelisted_and_violations():
    porcelain = (
        "?? 0_raw/commentaries/a.md\n"
        " M 1_extracted/relations/r.jsonl\n"
        "?? 0_raw/policies/p.md\n"
    )
    to_add, violations = classify_changes(porcelain, ["0_raw/commentaries/"])
    assert to_add == ["0_raw/commentaries/a.md"]
    assert sorted(violations) == ["0_raw/policies/p.md", "1_extracted/relations/r.jsonl"]


def test_classify_empty_porcelain_is_noop():
    assert classify_changes("", ["0_raw/commentaries/"]) == ([], [])


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def vault_with_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    vault = tmp_path / "vault"
    vault.mkdir()
    _git(["init", "-b", "main"], vault)
    _git(["config", "user.name", "t"], vault)
    _git(["config", "user.email", "t@t"], vault)
    (vault / "seed.md").write_text("seed", encoding="utf-8")
    _git(["add", "."], vault)
    _git(["commit", "-m", "seed"], vault)
    _git(["remote", "add", "origin", str(remote)], vault)
    _git(["push", "-u", "origin", "main"], vault)
    return vault


def test_run_commits_and_pushes_whitelisted_change(vault_with_remote):
    vault = vault_with_remote
    (vault / "0_raw" / "commentaries").mkdir(parents=True)
    (vault / "0_raw" / "commentaries" / "x.md").write_text("c", encoding="utf-8")
    rc = run(vault, ["0_raw/commentaries/"], "test: commentary batch")
    assert rc == 0
    local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=vault,
                           capture_output=True, text=True, check=True).stdout
    remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=vault,
                            capture_output=True, text=True, check=True).stdout
    assert local == remote


def test_run_noop_when_clean(vault_with_remote):
    assert run(vault_with_remote, ["0_raw/commentaries/"], "msg") == 0


def test_run_aborts_on_violation_without_commit(vault_with_remote, monkeypatch):
    alerts = []
    monkeypatch.setattr("scripts.service.produce_and_push.notify_send",
                        lambda m: alerts.append(m) or True)
    vault = vault_with_remote
    (vault / "rogue.md").write_text("x", encoding="utf-8")
    rc = run(vault, ["0_raw/commentaries/"], "msg")
    assert rc == 4
    assert alerts
    head_before = subprocess.run(["git", "log", "--oneline"], cwd=vault,
                                 capture_output=True, text=True, check=True).stdout
    assert head_before.count("\n") == 1  # 仍只有 seed 一个 commit


def test_run_keeps_local_commit_when_push_fails(vault_with_remote, monkeypatch):
    alerts = []
    monkeypatch.setattr("scripts.service.produce_and_push.notify_send",
                        lambda m: alerts.append(m) or True)
    vault = vault_with_remote
    _git(["remote", "set-url", "origin", str(vault / "nonexistent.git")], vault)
    (vault / "0_raw" / "commentaries").mkdir(parents=True)
    (vault / "0_raw" / "commentaries" / "y.md").write_text("c", encoding="utf-8")
    rc = run(vault, ["0_raw/commentaries/"], "msg")
    assert rc == 5
    assert alerts
    log = subprocess.run(["git", "log", "--oneline"], cwd=vault,
                         capture_output=True, text=True, check=True).stdout
    assert log.count("\n") == 2  # seed + 新 commit 保留
```

- [ ] Step 2: 跑测试确认失败:`python3 -m pytest tests/service/test_produce_and_push.py -q`
- [ ] Step 3: 最小实现:

```python
# scripts/service/produce_and_push.py
"""生产后 git 收尾:add(白名单)→ commit → pull --rebase → push。

所有生产 cron 共用。exit:0=成功/无变更;4=白名单外改动(告警不提交);
5=push 失败(本地 commit 保留,下轮重试;期间 sync_tick 守卫会 abort 不 reset)。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.service.notify import send_text as notify_send


def _git(args: list, cwd) -> str:
    res = subprocess.run(["git", *args], cwd=str(cwd), check=True,
                         capture_output=True, text=True)
    return res.stdout.strip()


def classify_changes(porcelain: str, whitelist: list) -> tuple:
    """git status --porcelain 输出 → (白名单内路径, 白名单外路径)。"""
    to_add, violations = [], []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:                     # rename: 取新路径
            path = path.split(" -> ", 1)[1].strip('"')
        (to_add if any(path.startswith(w) for w in whitelist) else violations).append(path)
    return to_add, violations


def run(vault_dir, whitelist: list, message: str) -> int:
    vault_dir = Path(vault_dir)
    porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=str(vault_dir),
                               check=True, capture_output=True, text=True).stdout
    to_add, violations = classify_changes(porcelain, whitelist)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if violations:
        msg = f"[produce_and_push] 白名单外改动,拒绝提交: {violations[:5]} (共{len(violations)})"
        print(f"[{ts}] {msg}", file=sys.stderr)
        notify_send(msg)
        return 4
    if not to_add:
        print(f"[{ts}] no change, skip")
        return 0
    _git(["add", "--", *to_add], vault_dir)
    _git(["commit", "-m", message], vault_dir)
    try:
        _git(["pull", "--rebase", "origin", "main"], vault_dir)
        _git(["push", "origin", "main"], vault_dir)
    except subprocess.CalledProcessError as e:
        msg = f"[produce_and_push] push 失败(本地 commit 保留待重试): {e.stderr[:200] if e.stderr else e}"
        print(f"[{ts}] {msg}", file=sys.stderr)
        notify_send(msg)
        return 5
    print(f"[{ts}] pushed {len(to_add)} paths: {message}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault-dir", required=True)
    ap.add_argument("--whitelist", required=True, help="逗号分隔路径前缀")
    ap.add_argument("--message", required=True)
    args = ap.parse_args(argv)
    return run(args.vault_dir, [w for w in args.whitelist.split(",") if w], args.message)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] Step 4: 跑测试确认过:`python3 -m pytest tests/service/test_produce_and_push.py -q`(预期 6 passed)
- [ ] Step 5: Commit:`git add scripts/service/produce_and_push.py tests/service/test_produce_and_push.py && git commit -m "feat(service): produce_and_push 生产后 git 收尾(白名单·rebase·失败保留)"`

### Task 3: commentary ingest `--since` 日期下限

**Files:**
- Modify: `scripts/l1_collect/commentary_ingest/run.py`(argparse + 过滤)
- Test: 追加到 `tests/commentary_signals/` 同级——实际放 `tests/l1_collect/test_ingest_since.py`(新文件)

规则:`--since YYYY-MM-DD`(env `WEWE_SINCE`);item.date_published **非空且 < since** → 跳过;date 为空的 item 保留(去重兜底)。

- [ ] Step 1: 写失败测试:

```python
# tests/l1_collect/test_ingest_since.py
from scripts.l1_collect.commentary_ingest.models import FeedItem
from scripts.l1_collect.commentary_ingest.run import filter_since


def _item(date):
    return FeedItem(id="x" * 22, url=f"https://mp.weixin.qq.com/s/{date or 'nodate'}",
                    title="t", content_html="<p>b</p>", date_published=date,
                    source_account="acc")


def test_filter_since_drops_older_keeps_newer_and_undated():
    items = [_item("2026-06-05"), _item("2026-06-07"), _item("2026-06-09"), _item("")]
    kept = filter_since(items, "2026-06-07")
    assert [i.date_published for i in kept] == ["2026-06-07", "2026-06-09", ""]


def test_filter_since_empty_threshold_keeps_all():
    items = [_item("2026-06-05"), _item("")]
    assert filter_since(items, "") == items
```

- [ ] Step 2: 跑测试确认失败(`ImportError: filter_since`)
- [ ] Step 3: 实现:run.py 加纯函数 + main 接线:

```python
def filter_since(items: list, since: str) -> list:
    """--since 下限:date 非空且 < since 的丢弃;date 为空保留(去重兜底)。"""
    if not since:
        return items
    return [i for i in items if not i.date_published or i.date_published >= since]
```

main() 中 argparse 加 `ap.add_argument("--since", default=os.environ.get("WEWE_SINCE", ""))`;`items = fetch_feed(...)` 之后插 `items = filter_since(items, args.since)`。

- [ ] Step 4: 跑测试确认过 + 全量回归:`python3 -m pytest tests/l1_collect/test_ingest_since.py tests/ -q`
- [ ] Step 5: Commit:`git commit -am "feat(ingest): --since 日期下限(存量边界以前的不抓)"`

### Task 4: fetcher 代理运行时兜底

**Files:**
- Modify: `scripts/l1_collect/fetcher.py`
- Test: `tests/l1_collect/test_fetcher_proxy.py`(新)

设计:直连链(firecrawl→trafilatura→bs4)全败且配了 `POLICY_FETCH_PROXY_URL` → 经代理重试 **trafilatura+bs4**(firecrawl 是云 API,代理我们的调用无意义,跳过);代理段 trafilatura 不用 `fetch_url`(不支持 proxies),改 `requests.get(proxies=...)` 拿 HTML 再 `trafilatura.extract`;`via` 记 `"trafilatura+proxy"` / `"bs4+proxy"`(即 spec 的 via_proxy 观测,以后缀实现);**只用显式 `proxies=` 参数,绝不写 os.environ**(纪律:同进程的 LLM gate 调用不得被波及)。

- [ ] Step 1: 写失败测试:

```python
# tests/l1_collect/test_fetcher_proxy.py
import os

from scripts.l1_collect import fetcher


def test_no_proxy_env_means_pure_direct_unchanged(monkeypatch):
    monkeypatch.delenv("POLICY_FETCH_PROXY_URL", raising=False)
    monkeypatch.setattr(fetcher, "_fetch_via_firecrawl", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_trafilatura", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_bs4", lambda url: None)
    r = fetcher.fetch_article("https://example.gov.cn/a")
    assert r.via == "fetch_error" and r.body is None


def test_proxy_retry_after_direct_exhausted(monkeypatch):
    monkeypatch.setenv("POLICY_FETCH_PROXY_URL", "http://proxy:1")
    monkeypatch.setattr(fetcher, "_fetch_via_firecrawl", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_trafilatura", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_bs4", lambda url: None)
    seen = {}

    def fake_proxy_fetch(url, proxy_url, extractor):
        seen["proxy"] = proxy_url
        return "正文" * 300

    monkeypatch.setattr(fetcher, "_fetch_via_proxy", fake_proxy_fetch)
    r = fetcher.fetch_article("https://example.gov.cn/a")
    assert r.via == "trafilatura+proxy"
    assert seen["proxy"] == "http://proxy:1"
    assert len(r.body) >= fetcher.MIN_BODY_LEN


def test_direct_success_never_touches_proxy(monkeypatch):
    monkeypatch.setenv("POLICY_FETCH_PROXY_URL", "http://proxy:1")
    monkeypatch.setattr(fetcher, "_fetch_via_firecrawl", lambda url: "正文" * 300)
    called = []
    monkeypatch.setattr(fetcher, "_fetch_via_proxy",
                        lambda *a, **k: called.append(1))
    r = fetcher.fetch_article("https://example.gov.cn/a")
    assert r.via == "firecrawl" and not called


def test_proxy_path_does_not_mutate_environ(monkeypatch):
    monkeypatch.setenv("POLICY_FETCH_PROXY_URL", "http://proxy:1")
    monkeypatch.setattr(fetcher, "_fetch_via_firecrawl", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_trafilatura", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_bs4", lambda url: None)
    monkeypatch.setattr(fetcher, "_fetch_via_proxy", lambda *a: None)
    fetcher.fetch_article("https://example.gov.cn/a")
    assert "HTTP_PROXY" not in os.environ and "HTTPS_PROXY" not in os.environ
```

- [ ] Step 2: 跑测试确认失败(`AttributeError: _fetch_via_proxy` 等)
- [ ] Step 3: 实现——fetcher.py 追加:

```python
def _extract_trafilatura(html: str):
    try:
        import trafilatura
        text = trafilatura.extract(html, include_comments=False, include_tables=True)
        return text if text and len(text) >= MIN_BODY_LEN else None
    except Exception:
        return None


def _extract_bs4(html: str):
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        return text if len(text) >= MIN_BODY_LEN else None
    except Exception:
        return None


def _fetch_via_proxy(url: str, proxy_url: str, extractor) -> Optional[str]:
    """经显式 proxies= 抓 HTML 后用指定抽取器。绝不写 os.environ。"""
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT,
                            proxies={"http": proxy_url, "https": proxy_url})
        if resp.status_code >= 400:
            return None
        return extractor(resp.text)
    except Exception:
        return None
```

`fetch_article` 改为:

```python
def fetch_article(url: str) -> FetchResult:
    for via, fn in [
        ("firecrawl", _fetch_via_firecrawl),
        ("trafilatura", _fetch_via_trafilatura),
        ("bs4", _fetch_via_bs4),
    ]:
        body = fn(url)
        if body:
            return FetchResult(url=url, via=via, body=body)
    proxy_url = os.environ.get("POLICY_FETCH_PROXY_URL", "")
    if proxy_url:
        for via, extractor in [
            ("trafilatura+proxy", _extract_trafilatura),
            ("bs4+proxy", _extract_bs4),
        ]:
            body = _fetch_via_proxy(url, proxy_url, extractor)
            if body:
                return FetchResult(url=url, via=via, body=body)
    return FetchResult(url=url, via="fetch_error", body=None)
```

- [ ] Step 4: 跑测试确认过 + 既有 fetcher 测试回归:`python3 -m pytest tests/l1_collect/ -q`
- [ ] Step 5: Commit:`git commit -am "feat(l1): fetcher 代理运行时兜底(直连尽→显式 proxies 重试·零配置·不写 environ)"`

### Task 5: L1→L2 队列接线(pid 贯通)

**Files:**
- Modify: `scripts/l1_collect/ingester.py`(`ingest_one` 返回值加 pid)
- Modify: `scripts/l1_collect/step5_ingest.py`(日志记 pid,返回 pid 列表)
- Modify: `scripts/l1_collect/run_incremental.py`(收集 pid → `enqueue_batch`;加 `--vault-dir` / `--l2-queue` 参数)
- Test: `tests/l1_collect/test_l1_to_l2_enqueue.py`(新)

注意:`ingest_one` 现返回 `md_path`;改为返回 `(md_path, pid)` 需同步更新所有调用方(先 `grep -rn "ingest_one(" scripts/ tests/`,逐个改;已知调用方:step5_ingest)。`ingest_extracted` 返回 `(ingested, failed)` 改为 `(ingested, failed, pids)`——同样先 grep 调用方(已知:run_incremental 两处,解包 `ing_ok, _` 改 `ing_ok, _, pids`;`_ingest_commentary` 内的调用丢弃第三元即可)。

- [ ] Step 1: 写失败测试:

```python
# tests/l1_collect/test_l1_to_l2_enqueue.py
import json
from pathlib import Path

from scripts.service.l2_queue import read_queue
from scripts.l1_collect.run_incremental import enqueue_ingested


def test_enqueue_ingested_writes_queue_items(tmp_path):
    q = tmp_path / "l2_queue.jsonl"
    enqueue_ingested(q, ["P-001", "P-002"], requested_at="2026-06-10T09:00:00+08:00")
    items = read_queue(q)
    assert [i.pid for i in items] == ["P-001", "P-002"]
    assert all(i.trigger == "l1_incremental" and i.priority == "normal" for i in items)


def test_enqueue_ingested_empty_is_noop(tmp_path):
    q = tmp_path / "l2_queue.jsonl"
    enqueue_ingested(q, [], requested_at="2026-06-10T09:00:00+08:00")
    assert not q.exists()
```

- [ ] Step 2: 跑确认失败(`ImportError: enqueue_ingested`)
- [ ] Step 3: 实现:
  - `ingest_one`:`return fn` → `return fn, pid`(函数内 pid 已算好)
  - `step5_ingest.ingest_extracted`:`md_path = ingest_one(...)` → `md_path, pid = ingest_one(...)`;ok 分支 `logs.append({..., "pid": pid})` 并收集 `pids.append(pid)`;返回 `(ingested, failed, pids)`
  - `run_incremental.py` 顶部 `from scripts.service.l2_queue import enqueue_batch`;加:

```python
def enqueue_ingested(queue_path: Path, pids: list, *, requested_at: str) -> None:
    """L1 新入库 pid → L2 队列(trigger=l1_incremental)。空列表 no-op。"""
    if not pids:
        return
    enqueue_batch(Path(queue_path), pids, "l1_incremental", "normal", requested_at)
```

  - `_run_channel`:`ing_ok, _, pids = ingest_extracted(...)`,结果 dict 加 `"pids": pids`
  - `run_incremental()`:循环后 `all_pids = [p for r in results for p in r.get("pids", [])]`,非 dry 时 `enqueue_ingested(cfg.l2_queue_path, all_pids, requested_at=datetime.now(CST).isoformat())`;`IncrementalConfig` 加字段 `l2_queue_path: Path = STATE / "l2_queue.jsonl"`
  - `main()` argparse 加 `--vault-dir`(default 现 Mac 路径)与 `--l2-queue`(default `state/l2_queue.jsonl`),传入 config
- [ ] Step 4: 跑新测试 + 全量回归:`python3 -m pytest tests/ -q`
- [ ] Step 5: Commit:`git commit -am "feat(l1): 入库 pid 贯通→L2 队列接线;run_incremental 加 --vault-dir/--l2-queue"`

### Task 6: route_interpretations 出 _oneshot 转正

**Files:**
- Move: `scripts/_oneshot/route_interpretations.py` → `scripts/l1_collect/route_interpretations.py`
- Modify: `scripts/l1_collect/run_incremental.py:108`(import 改 `from .route_interpretations import route_files, build_title_index`)

理由:每日 cron 会日日调它,按仓纪律"oneshot 跑 ≥2 次必转正"。

- [ ] Step 1: `grep -rn "route_interpretations" scripts/ tests/ --include="*.py"` 列出全部引用
- [ ] Step 2: `git mv scripts/_oneshot/route_interpretations.py scripts/l1_collect/route_interpretations.py`;改所有 import
- [ ] Step 3: 全量回归:`python3 -m pytest tests/ -q`;确认 `python3 -c "from scripts.l1_collect.run_incremental import main"` 可导入
- [ ] Step 4: Commit:`git commit -am "refactor(l1): route_interpretations 出 _oneshot 转正(进每日 cron 路径)"`

### Task 7: compose 加 producer 服务(vault 可写)

**Files:**
- Modify: `docker-compose.server.yml`

现 `policy-pipeline` 服务挂 `vault:ro`(投影消费用,保持不动)。加 `policy-producer`:同镜像、vault **rw**、env_file 多挂 models.env;**fetch-proxy/notify env 不进 env_file**(代理按纪律仅 cron 行内 `-e` 注入 L1;notify 是 host 层的事)。

- [ ] Step 1: 在 `docker-compose.server.yml` `services:` 下追加:

```yaml
  policy-producer:
    image: policy-pipeline:latest
    env_file:
      - /etc/policy-pipeline/pipeline.env
      - /etc/policy-pipeline/models.env
    volumes:
      - /root/policy-vault:/vault          # 生产线需写 vault(raw 只增不删纪律仍由代码层守)
      - /root/policy-pipeline-state:/state
    networks: [platform-net]
    restart: "no"
    # 无默认 command;由 cron `docker compose run --rm policy-producer python -m ...` 指定
```

- [ ] Step 2: 本地语法验证:`docker compose -f docker-compose.server.yml config -q`(无 docker 的环境跳过,W0.2 服务器端验证)
- [ ] Step 3: Commit:`git commit -am "feat(deploy): compose 加 policy-producer 服务(vault rw·挂 models.env)"`

### Task 8: 服务器 cron 接线(部署文档化)

**Files:**
- Create: `docs/runbooks/s2-vps-cron.md`(crontab 全文 + 验证命令,部署时照抄)

- [ ] Step 1: 写 runbook,crontab 内容如下(`OPSDIR=/root/policy-pipeline-src`,全部行尾带告警兜底;notify env 用 `BASH_ENV` 风格 source):

```cron
SHELL=/bin/bash
# ── S2 单生产者编排(时间均 CST;服务器 TZ 先确认,若 UTC 需 -8h 换算)──
# 07:30 评论 ingest(容器,经 platform-net 服务名访问 wewe-rss,见 Task 0.5)→ vault → push
# (省略 --db-path = 跳过容器内 token 检查;token 检查由 host 每 6h 独立条目负责)
30 7 * * * set -a; . /etc/policy-pipeline/notify.env; . /etc/policy-pipeline/commentary.env; set +a; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm -e WEWE_FEED_URL -e WEWE_AUTH_CODE policy-producer python -m scripts.l1_collect.commentary_ingest.run --feed-url "$WEWE_FEED_URL" --auth-code "$WEWE_AUTH_CODE" --vault-dir /vault --state-dir /state --since 2026-06-07 >> /var/log/policy-pipeline/ingest.log 2>&1 && /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault --whitelist 0_raw/commentaries/ --message "l1(commentary): daily ingest" >> /var/log/policy-pipeline/ingest.log 2>&1 || /usr/bin/python3 -m scripts.service.notify "[S2] 07:30 评论 ingest 失败,查 ingest.log"

# 09:00 L1 政策增量(容器)→ vault → push(W3 验证后启用,先注释)
#0 9 * * * set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.l1_collect.run_incremental --vault-dir /vault/0_raw/policies --l2-queue /state/l2_queue.jsonl >> /var/log/policy-pipeline/l1.log 2>&1 && /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault --whitelist 0_raw/policies/,0_raw/commentaries/ --message "l1(policy): daily incremental" >> /var/log/policy-pipeline/l1.log 2>&1 || /usr/bin/python3 -m scripts.service.notify "[S2] 09:00 L1 失败,查 l1.log"

# 09:30 L2 drain(容器)→ vault → push(W2 验证后启用,先注释)
#30 9 * * * set -a; . /etc/policy-pipeline/notify.env; set +a; cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.service.run_l2 --vault /vault --state-dir /state --gen-model MiniMax-M2.7-highspeed --gen-provider anthropic --judge-model deepseek-v4-flash --judge-provider openai >> /var/log/policy-pipeline/l2.log 2>&1 && /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault --whitelist 1_extracted/,_meta/business_view/,2_crystallized/ --message "l2: daily derive" >> /var/log/policy-pipeline/l2.log 2>&1 || /usr/bin/python3 -m scripts.service.notify "[S2] 09:30 L2 失败,查 l2.log"

# 10:00 投影(生产完即投)
0 10 * * * cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-pipeline python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1 >> /var/log/policy-pipeline/sync_tick.log 2>&1 || { set -a; . /etc/policy-pipeline/notify.env; set +a; /usr/bin/python3 -m scripts.service.notify "[S2] 10:00 投影失败"; }

# 09:30 QR relay 哨兵(host venv;含 account.add 落库修复)
30 9 * * * set -a; . /etc/policy-pipeline/notify.env; . /etc/policy-pipeline/commentary.env; set +a; cd /root/policy-pipeline-src && /root/policy-sentinel-venv/bin/python -m scripts.l1_collect.commentary_ingest.qr_relay.daily_check --db-path /root/wewe-rss/data/wewe-rss.db --qr-dir /root/policy-pipeline-state/wewe_qr --target "$OPENCLAW_IM_TARGET" >> /var/log/policy-pipeline/qr_relay.log 2>&1

# 每 6h token 检测(纯文字告警,免费)
0 */6 * * * set -a; . /etc/policy-pipeline/notify.env; . /etc/policy-pipeline/commentary.env; set +a; cd /root/policy-pipeline-src && /root/policy-sentinel-venv/bin/python -m scripts.l1_collect.commentary_ingest.run --check-token --db-path /root/wewe-rss/data/wewe-rss.db >> /var/log/policy-pipeline/token.log 2>&1 || /usr/bin/python3 -m scripts.service.notify "[S2] wewe token 失效,QR 哨兵将于 09:30 推码"

# 21:00 sync_tick 兜底(既有,不动)
```

  哨兵 venv 一次性建:`python3 -m venv /root/policy-sentinel-venv && /root/policy-sentinel-venv/bin/pip install requests qrcode trafilatura beautifulsoup4 pyyaml`
  (注:`--check-token` 走 run.py 顶层 import,需要 trafilatura——故 venv 一并装;`--db-path /dev/null` 的容器 ingest 行不做 token 检查,token 检查独立条目在 host 做)
- [ ] Step 2: Commit:`git add docs/runbooks/s2-vps-cron.md && git commit -m "docs(s2): VPS cron 接线 runbook"`

---

## W1–W4 · 上线波次(部署 + 验证)

### Task 9 (W1): 评论线全自动

- [ ] Step 1: W0 全清(0.1–0.4)
- [ ] Step 2: **监督首跑**(--since 2026-06-07,人在场):跑 Task 8 runbook 里 07:30 那条的命令体(手动执行一遍),观察 summary JSON
- [ ] Step 3: 验证四件:① vault `git -C /root/policy-vault log -1` 出现 commentary commit 且已 push;② GitHub origin/main 同 HEAD;③ `run_sync` 跑一次投影 `last_sync_run.json` errors=[];④ 飞书无告警
- [ ] Step 4: crontab 加 07:30/09:30(QR)/6h(token)/10:00(投影)四条(09:00/09:30-L2 仍注释)
- [ ] Step 5: Mac 退岗:`launchctl unload ~/Library/LaunchAgents/com.zayn.policy.wewe-qr-relay-daily.plist`(用户)
- [ ] Step 6: 次日核 cron 自跑结果(日志 + vault log + 飞书静默=健康)

### Task 10 (W2): L2 + 投影链

- [ ] Step 1: 人工 enqueue 1-2 个新 pid(或等 W3 L1 喂)→ `docker compose run --rm policy-producer python -m scripts.service.run_l2 ...`(监督)
- [ ] Step 2: 验证:派生文件落 vault 白名单路径、produce_and_push 成功、投影 errors=[]
- [ ] Step 3: crontab 解开 09:30 L2 条目

### Task 11 (W3): 政策线(含用户手动验证轮)

- [ ] Step 1: `docker compose run --rm policy-producer python -m scripts.l1_collect.run_incremental --vault-dir /vault/0_raw/policies --l2-queue /state/l2_queue.jsonl --dry-run`(看 scanned/kept,零写入)
- [ ] Step 2: **用户手动触发一轮完整 L1**(监督真跑):同命令去掉 --dry-run;盯 gate 判定、review_pool、ingested 数
- [ ] Step 3: 人工抽查:新入库 .md 的 frontmatter/正文质量、`state/l1_gate/gate_calls.jsonl` 判定合理性、有无该走代理的 fetch_error(看 via 分布)
- [ ] Step 4: produce_and_push 政策白名单 → 投影 → L2 队列有新 pid → run_l2 消化
- [ ] Step 5: crontab 解开 09:00 条目;首周每日人工看一眼 l1.log + review_pool
- [ ] Step 6: (按需)若有长尾渠道持续 fetch_error,给 09:00 行加 `-e POLICY_FETCH_PROXY_URL`(source fetch-proxy.env 后传入;仅此一行,纪律)

### Task 12 (W4): cutover 收尾

- [ ] Step 1: drift 核对:`dump_status.py` + vault 双端 HEAD 一致 + DB 计数对账
- [ ] Step 2: OPERATIONS.md 改版:§3 维护期标"已启用(VPS)",§8 重写为单生产者数据流(producer=VPS),Changelog v0.5
- [ ] Step 3: memory 更新(commentary-rss-ingest-line / migration-s2 标"S2 已落地")
- [ ] Step 4: Mac 退役清单:无 crontab(已确认)、launchd 已卸、vault 仅 `git pull` 只读;CLAUDE.md 评论节补一行"已迁 VPS"
- [ ] Step 5: 全部 commit + 合 main

---

## Self-Review 备忘(已核)

- spec §3.1–3.6 → Task 2/3/4/5/1/8 一一对应;§4 → Task 0.3;§5 波次 → Task 0.x/9/10/11/12;Task 0.5/6/7 为 plan 期新发现(网络拓扑/oneshot 转正/挂载只读)的必要补件
- ingest cron 行省略 `--db-path` ⇒ run.py `st=None` 跳过 token 检查(host 每 6h 独立条目负责);`--network host` 方案已废弃(compose run 不支持),改 Task 0.5 共网方案
- 类型一致:`enqueue_batch(path, pids, trigger, priority, requested_at)` 与 l2_queue.py:52 签名一致;`classify_changes` 输入 porcelain 文本与 sync_tick `_git(["status","--porcelain"])` 输出一致
- 服务器 TZ:cron 时刻按 CST 设计,部署时 `timedatectl` 确认,若 UTC 全部 -8h
