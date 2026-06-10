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
