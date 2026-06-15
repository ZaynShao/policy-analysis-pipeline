import subprocess
from pathlib import Path

import pytest

from scripts.service.produce_and_push import classify_changes, run


def test_classify_splits_whitelisted_and_violations():
    porcelain = (                              # -z:NUL 分隔
        "?? 0_raw/commentaries/a.md\0"
        " M 1_extracted/relations/r.jsonl\0"
        "?? 0_raw/policies/p.md\0"
    )
    to_add, violations = classify_changes(porcelain, ["0_raw/commentaries/"])
    assert to_add == ["0_raw/commentaries/a.md"]
    assert sorted(violations) == ["0_raw/policies/p.md", "1_extracted/relations/r.jsonl"]


def test_classify_empty_porcelain_is_noop():
    assert classify_changes("", ["0_raw/commentaries/"]) == ([], [])


def test_classify_z_handles_control_char_filename():
    # git status --porcelain -z:NUL 分隔、文件名不转义;名内真实换行/制表符不得拆条目
    porcelain = "?? 0_raw/policies/a\nb\t(26).md\0?? 0_raw/commentaries/c.md\0"
    to_add, violations = classify_changes(porcelain, ["0_raw/policies/"])
    assert to_add == ["0_raw/policies/a\nb\t(26).md"]
    assert violations == ["0_raw/commentaries/c.md"]


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


def test_run_handles_chinese_and_space_filenames(vault_with_remote):
    vault = vault_with_remote
    (vault / "0_raw" / "commentaries").mkdir(parents=True)
    (vault / "0_raw" / "commentaries" / "储能价值 最大化—难在哪.md").write_text("c", encoding="utf-8")
    rc = run(vault, ["0_raw/commentaries/"], "test: chinese filename")
    assert rc == 0
    remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=vault,
                            capture_output=True, text=True, check=True).stdout
    local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=vault,
                           capture_output=True, text=True, check=True).stdout
    assert local == remote


def test_run_commits_control_char_filename_without_crash(vault_with_remote):
    vault = vault_with_remote
    (vault / "0_raw" / "policies").mkdir(parents=True)
    # 文件名内嵌真实换行/制表符(市监 backfill 误抓那类)→ 旧实现 git add 退 128 崩
    (vault / "0_raw" / "policies" / "x\n\ty.md").write_text("p", encoding="utf-8")
    rc = run(vault, ["0_raw/policies/"], "test: control-char filename")
    assert rc == 0
    remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=vault,
                            capture_output=True, text=True, check=True).stdout
    local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=vault,
                           capture_output=True, text=True, check=True).stdout
    assert local == remote


def test_run_aborts_rebase_on_conflict_leaving_clean_tree(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.service.produce_and_push.notify_send",
                        lambda m: True)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    # clone A(本地 vault)
    vault = tmp_path / "vault"
    subprocess.run(["git", "clone", str(remote), str(vault)], check=True, capture_output=True)
    _git(["config", "user.name", "t"], vault)
    _git(["config", "user.email", "t@t"], vault)
    _git(["checkout", "-b", "main"], vault)
    (vault / "0_raw" / "commentaries").mkdir(parents=True)
    (vault / "0_raw" / "commentaries" / "c.md").write_text("base", encoding="utf-8")
    _git(["add", "."], vault)
    _git(["commit", "-m", "base"], vault)
    _git(["push", "-u", "origin", "main"], vault)
    # clone B 推一个冲突版本
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True)
    _git(["config", "user.name", "o"], other)
    _git(["config", "user.email", "o@o"], other)
    (other / "0_raw" / "commentaries" / "c.md").write_text("theirs", encoding="utf-8")
    _git(["add", "."], other)
    _git(["commit", "-m", "theirs"], other)
    _git(["push", "origin", "main"], other)
    # 本地 vault 改同一文件 → run → rebase 冲突 → 应 exit 5 且树干净(rebase 已 abort)
    (vault / "0_raw" / "commentaries" / "c.md").write_text("ours", encoding="utf-8")
    rc = run(vault, ["0_raw/commentaries/"], "ours change")
    assert rc == 5
    assert not (vault / ".git" / "rebase-merge").exists()
    assert not (vault / ".git" / "rebase-apply").exists()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=vault,
                            capture_output=True, text=True, check=True).stdout
    assert status.strip() == ""  # 树干净:本地 commit 保留在 HEAD,无 UU 残留


def test_run_retries_stranded_commit_on_quiet_round(vault_with_remote, monkeypatch):
    monkeypatch.setattr("scripts.service.produce_and_push.notify_send",
                        lambda m: True)
    vault = vault_with_remote
    good_url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=vault,
                              capture_output=True, text=True, check=True).stdout.strip()
    _git(["remote", "set-url", "origin", str(vault / "nonexistent.git")], vault)
    (vault / "0_raw" / "commentaries").mkdir(parents=True)
    (vault / "0_raw" / "commentaries" / "z.md").write_text("c", encoding="utf-8")
    assert run(vault, ["0_raw/commentaries/"], "first try") == 5   # push 失败,commit 滞留
    _git(["remote", "set-url", "origin", good_url], vault)
    assert run(vault, ["0_raw/commentaries/"], "quiet round") == 0  # 安静轮重推成功
    local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=vault,
                           capture_output=True, text=True, check=True).stdout
    remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=vault,
                            capture_output=True, text=True, check=True).stdout
    assert local == remote
