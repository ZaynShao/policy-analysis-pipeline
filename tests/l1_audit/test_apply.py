import textwrap, yaml
from pathlib import Path
from scripts.l1_audit.apply import archive_policy, move_duplicate

def _mk(dir_, fname, pid, extra=""):
    dir_.mkdir(parents=True, exist_ok=True)
    fm = f"id: {pid}\ntitle: t{pid}\n{extra}"
    (dir_ / fname).write_text(f"---\n{fm}\n---\n\n## 政策原文\n正文\n", encoding="utf-8")

def test_archive_policy_moves_file(tmp_path):
    pol = tmp_path / "0_raw" / "policies"
    _mk(pol, "noise.md", "P_2026_X_noise")
    arch = tmp_path / "0_raw" / "_archive" / "policies" / "source_audit_2026-05-30"
    dst = archive_policy(str(pol), "P_2026_X_noise", str(arch))
    assert Path(dst).exists()
    assert not (pol / "noise.md").exists()       # 原位已移走
    assert "_archive" in dst

def test_move_duplicate_adds_fields_and_moves(tmp_path):
    pol = tmp_path / "0_raw" / "policies"
    _mk(pol, "keep.md", "P_A")
    _mk(pol, "dup.md", "P_B")
    dups = tmp_path / "0_raw" / "_duplicates"
    dst = move_duplicate(str(pol), "P_B", "P_A", str(dups), "2026-05-30T00:00:00")
    assert Path(dst).exists()
    assert not (pol / "dup.md").exists()
    fm = yaml.safe_load(Path(dst).read_text(encoding="utf-8").split("---")[1])
    assert fm["_duplicate_of"] == "P_A"
    assert fm["dedup_at"] == "2026-05-30T00:00:00"
    assert fm["dedup_rule"]                       # 非空
    assert fm["id"] == "P_B"                       # 原字段保留
    assert "## 政策原文" in Path(dst).read_text(encoding="utf-8")  # body 保留
