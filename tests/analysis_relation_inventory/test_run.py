import json
import subprocess

from scripts.analysis_relation_inventory.run import run_preview


def _write_policy(path, policy_id, aliases=None, title="政策标题"):
    aliases = aliases or []
    path.parent.mkdir(parents=True, exist_ok=True)
    alias_lines = "\n".join(f"  - {alias}" for alias in aliases)
    aliases_block = f"aliases:\n{alias_lines}\n" if aliases else "aliases: []\n"
    path.write_text(
        "---\n"
        f"id: {policy_id}\n"
        f"{aliases_block}"
        f"title: {title}\n"
        "---\n"
        "## 政策原文\n正文",
        encoding="utf-8",
    )


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def test_preview_indexes_only_tracked_raw_and_reports_untracked(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    vault.mkdir()
    _init_git_repo(vault)
    _write_policy(vault / "0_raw" / "policies" / "tracked.md", "P_2025_OK_1", aliases=["P_OLD_1"])
    _write_policy(vault / "0_raw" / "policies" / "untracked.md", "P_2025_UNTRACKED_1")
    _write_jsonl(
        vault / "1_extracted" / "relations" / "references.jsonl",
        [{"from": "P_2025_OK_1", "to": "P_OLD_1", "rel": "references", "confidence": 0.9}],
    )
    subprocess.run(["git", "add", "0_raw/policies/tracked.md", "1_extracted/relations/references.jsonl"], cwd=vault, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=vault, check=True, stdout=subprocess.DEVNULL)

    result = run_preview(vault, state)

    summary = result["summary"]
    assert summary["tracked_policy_count"] == 1
    assert summary["untracked_policy_count"] == 1
    assert summary["relation_rows"] == 1
    rows = _read_jsonl(state / "relation_rows.jsonl")
    assert rows[0]["from_status"] == "located"
    assert rows[0]["to_status"] == "located"
    assert rows[0]["to_locator"]["matched_by"] == "alias"
    html = (state / "reports" / "relation_inventory_preview.html").read_text(encoding="utf-8")
    assert "未跟踪 raw 已排除" in html


def test_preview_flags_missing_p1900_archive_and_relation_family(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    vault.mkdir()
    _init_git_repo(vault)
    _write_policy(vault / "0_raw" / "policies" / "a.md", "P_1900_GO_abc")
    _write_policy(vault / "0_raw" / "policies" / "b.md", "P_2025_OK_2")
    _write_jsonl(
        vault / "1_extracted" / "relations" / "derives_from.jsonl",
        [{"from": "P_1900_GO_abc", "to": "P_MISSING", "rel": "derives_from", "confidence": 0.4}],
    )
    _write_jsonl(
        vault / "1_extracted" / "relations" / "_archive_old.jsonl",
        [{"from": "P_2025_OK_2", "to": "P_1900_GO_abc", "rel": "references", "confidence": 0.7}],
    )
    subprocess.run(["git", "add", "."], cwd=vault, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=vault, check=True, stdout=subprocess.DEVNULL)

    run_preview(vault, state)

    rows = _read_jsonl(state / "relation_rows.jsonl")
    derives = next(row for row in rows if row["relation_file"] == "derives_from.jsonl")
    archived = next(row for row in rows if row["relation_file"] == "_archive_old.jsonl")
    assert derives["from_status"] == "located"
    assert derives["to_status"] == "missing"
    assert {"from_p1900", "to_missing", "semantic_low_confidence"}.issubset(set(derives["flags"]))
    assert {"archive_relation_file", "high_precision_candidate"}.issubset(set(archived["flags"]))

    summary = json.loads((state / "relation_inventory.json").read_text(encoding="utf-8"))
    assert summary["rows_by_relation"]["derives_from"] == 1
    assert summary["rows_by_flag"]["archive_relation_file"] == 1
    assert summary["endpoint_missing_count"] == 1
    assert (state / "reports" / "relation_inventory_preview.html").exists()
