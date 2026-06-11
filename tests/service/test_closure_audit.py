import json
import os
import subprocess
import time
from pathlib import Path

from scripts.service import closure_audit


def _touch(path: Path, age_hours: float = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    ts = time.time() - age_hours * 3600
    os.utime(path, (ts, ts))


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _commit(repo: Path, path: str, author: str = "policy-pipeline-vps") -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{path}\n{time.time()}\n", encoding="utf-8")
    _run_git(repo, "add", path)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": f"{author}@example.test",
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": f"{author}@example.test",
    }
    subprocess.check_call(["git", "commit", "-m", f"add {path}"], cwd=repo, env=env)
    return _run_git(repo, "rev-parse", "--short", "HEAD")


def _make_state_dir(tmp_path: Path) -> Path:
    state_dir = tmp_path / "state"
    for rel, _hours in closure_audit.STATE_THRESHOLDS_HOURS:
        _touch(state_dir / rel)
    (state_dir / "last_sync_run.json").write_text(
        json.dumps({"errors": []}),
        encoding="utf-8",
    )
    return state_dir


def _make_vault_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "vault"
    repo.mkdir()
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "remote", "add", "origin", str(tmp_path / "origin.git"))
    _run_git(tmp_path, "init", "--bare", "origin.git")
    _commit(repo, "README.md")
    _run_git(repo, "push", "-u", "origin", "main")
    return repo


def _healthy_fixture(tmp_path: Path) -> tuple[Path, Path]:
    state_dir = _make_state_dir(tmp_path)
    vault = _make_vault_repo(tmp_path)
    return state_dir, vault


def test_state_mtime_flags_missing_and_stale_files(tmp_path):
    state_dir = _make_state_dir(tmp_path)
    (state_dir / "derived_signals/nightly").unlink()
    _touch(state_dir / "relations_increment/hpr", age_hours=27)

    violations = closure_audit.check_state_activity(state_dir, now=time.time())

    assert any("derived_signals/nightly" in item and "缺失" in item for item in violations)
    assert any("relations_increment/hpr" in item and "超龄" in item for item in violations)
    assert not any("commentary_ingest/last_run.json" in item for item in violations)


def test_state_activity_flags_last_sync_errors(tmp_path):
    state_dir = _make_state_dir(tmp_path)
    (state_dir / "last_sync_run.json").write_text(
        json.dumps({"errors": ["boom"]}),
        encoding="utf-8",
    )

    violations = closure_audit.check_state_activity(state_dir, now=time.time())

    assert any("last_sync_run.json" in item and "errors" in item for item in violations)


def test_vault_git_flags_dirty_tree_and_head_drift(tmp_path):
    _state_dir, vault = _healthy_fixture(tmp_path)
    (vault / "README.md").write_text("dirty\n", encoding="utf-8")
    violations = closure_audit.check_vault_git(vault)
    assert any("工作树不干净" in item for item in violations)

    _run_git(vault, "checkout", "--", "README.md")
    _commit(vault, "0_raw/policies/new.md")
    _run_git(vault, "push", "origin", "main")
    _run_git(vault, "reset", "--hard", "HEAD~1")
    violations = closure_audit.check_vault_git(vault)
    assert any("HEAD != origin/main" in item for item in violations)


def test_vault_git_flags_non_vps_author_touching_product_path(tmp_path):
    _state_dir, vault = _healthy_fixture(tmp_path)
    bad_hash = _commit(vault, "_meta/business_view/item.json", author="human-user")
    _run_git(vault, "push", "origin", "main")

    violations = closure_audit.check_vault_git(vault)

    assert any(bad_hash in item and "human-user" in item for item in violations)
    assert any("_meta/business_view/item.json" in item for item in violations)


def test_vault_git_allows_non_vps_author_touching_non_product_path(tmp_path):
    _state_dir, vault = _healthy_fixture(tmp_path)
    _commit(vault, "docs/note.md", author="human-user")
    _run_git(vault, "push", "origin", "main")

    violations = closure_audit.check_vault_git(vault)

    assert violations == []


def test_cli_dry_run_prints_violations_without_notifying(tmp_path, monkeypatch, capsys):
    state_dir, vault = _healthy_fixture(tmp_path)
    (state_dir / "commentary_ingest/last_run.json").unlink()
    sent = []
    monkeypatch.setattr(closure_audit.notify, "send_text", lambda msg: sent.append(msg) or True)

    rc = closure_audit.main(
        ["--vault", str(vault), "--state-dir", str(state_dir), "--dry-run"]
    )

    out = capsys.readouterr().out
    assert rc == 1
    assert "commentary_ingest/last_run.json" in out
    assert sent == []


def test_cli_notifies_and_exits_one_on_violations(tmp_path, monkeypatch):
    state_dir, vault = _healthy_fixture(tmp_path)
    (state_dir / "signal_context/nightly").unlink()
    sent = []
    monkeypatch.setattr(closure_audit.notify, "send_text", lambda msg: sent.append(msg) or True)

    rc = closure_audit.main(["--vault", str(vault), "--state-dir", str(state_dir)])

    assert rc == 1
    assert len(sent) == 1
    assert sent[0].startswith("[S2] 闭环巡检异常 1 项:")
    assert "signal_context/nightly" in sent[0]


def test_cli_prints_json_and_does_not_notify_when_healthy(tmp_path, monkeypatch, capsys):
    state_dir, vault = _healthy_fixture(tmp_path)
    sent = []
    monkeypatch.setattr(closure_audit.notify, "send_text", lambda msg: sent.append(msg) or True)

    rc = closure_audit.main(["--vault", str(vault), "--state-dir", str(state_dir)])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["ok"] is True
    assert out["checked"] == {
        "state_paths": 6,
        "vault_product_commits": 0,
    }
    assert sent == []
