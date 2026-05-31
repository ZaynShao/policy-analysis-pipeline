"""apply 2b 编排集成测:dedup / archive / remint(就地) / market_intel(只登记) / commentary_defer(只 log)。"""
import json
from pathlib import Path
from scripts.l1_audit.apply_2b import run_2b
from scripts.l1_audit.apply import _FM_RE
import yaml


def _write(policies: Path, pid, title=None, issuer="国务院办公厅", date="2024-01-01"):
    title = title or pid
    fm = (f"---\nid: {pid}\ntitle: {title}\nofficial_number: 发改〔2024〕1号\n"
          f"date: '{date}'\nissuer: {issuer}\nissuer_canonical: [go]\n"
          f"source_url: https://x.gov.cn/{pid}.html\n---\n\n## 政策原文\n正文。\n")
    (policies / f"{pid}.md").write_text(fm, encoding="utf-8")


def test_run_2b_full_flow(tmp_path):
    vault = tmp_path / "vault"
    policies = vault / "0_raw" / "policies"
    policies.mkdir(parents=True)
    archive_dir = vault / "0_raw" / "_archive" / "policies" / "source_audit_2b_2026-05-31"
    duplicates_dir = vault / "0_raw" / "_duplicates"

    _write(policies, "P_KEEP")
    _write(policies, "P_DUP")
    _write(policies, "P_NOISE")
    _write(policies, "P_REMINT", issuer="国务院办公厅", date="2024-01-01")
    _write(policies, "P_MI")
    _write(policies, "P_COMMENT")

    decisions = {
        "date": "2026-05-31",
        "dedup": [{"move": "P_DUP", "keep": "P_KEEP"}],
        "archive": [{"pid": "P_NOISE", "reason": "导航壳真噪声"}],
        "remint": [{"pid": "P_REMINT", "new_id": "P_2024_GD_x", "id_short": "GD",
                    "true_issuer": "广州市人民政府", "true_region": "广州市"}],
        "market_intel": [{"pid": "P_MI", "title_evidence": "某储能项目清单公示"}],
        "commentary_defer": [{"pid": "P_COMMENT", "note": "解读非原文"}],
        "unresolved": [],
    }
    manifest = tmp_path / "out" / "market_intel_manifest.jsonl"
    log = tmp_path / "out" / "apply_log_2b.jsonl"

    summary = run_2b(str(policies), str(archive_dir), str(duplicates_dir),
                     str(manifest), str(log), decisions)

    # dedup: 迁走 + _duplicate_of 写对
    assert not (policies / "P_DUP.md").exists()
    assert (duplicates_dir / "P_DUP.md").exists()
    assert "_duplicate_of: P_KEEP" in (duplicates_dir / "P_DUP.md").read_text(encoding="utf-8")

    # archive: 迁到 archive_dir、原位消失
    assert not (policies / "P_NOISE.md").exists()
    assert (archive_dir / "P_NOISE.md").exists()

    # remint: 就地、仍在 policies/、id 改了
    assert (policies / "P_REMINT.md").exists()
    m = _FM_RE.search((policies / "P_REMINT.md").read_text(encoding="utf-8"))
    fm = yaml.safe_load(m.group(1))
    assert fm["id"] == "P_2024_GD_x"
    assert "P_REMINT" in fm["aliases"]
    assert fm["id_fixed_at"] == "2026-05-31"

    # market_intel: 原位不动
    assert (policies / "P_MI.md").exists()
    # commentary_defer: 文件不动
    assert (policies / "P_COMMENT.md").exists()

    # manifest 只 1 条
    mani = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(mani) == 1
    assert mani[0]["pid"] == "P_MI"
    assert mani[0]["class"] == "market_intel"

    # log 含全部 action
    log_lines = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    actions = {e["action"] for e in log_lines}
    assert actions == {"dedup_move", "archive", "remint", "market_intel", "commentary_defer"}

    assert summary == {"dedup_moved": 1, "archived": 1, "reminted": 1,
                       "market_intel": 1, "commentary_defer": 1}


def test_run_2b_manifest_idempotent(tmp_path):
    vault = tmp_path / "vault"
    policies = vault / "0_raw" / "policies"
    policies.mkdir(parents=True)
    _write(policies, "P_MI")

    manifest = tmp_path / "out" / "market_intel_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    # 预置 2a 已写的同 pid 行
    manifest.write_text(
        json.dumps({"pid": "P_MI", "class": "market_intel"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    log = tmp_path / "out" / "apply_log_2b.jsonl"

    decisions = {"date": "2026-05-31",
                 "market_intel": [{"pid": "P_MI", "title_evidence": "x"}]}
    run_2b(str(policies), str(tmp_path / "arch"), str(tmp_path / "dup"),
           str(manifest), str(log), decisions)

    lines = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    pids = [l["pid"] for l in lines]
    assert pids.count("P_MI") == 1
