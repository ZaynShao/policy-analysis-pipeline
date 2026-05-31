"""apply 2a 编排集成测:小 fixture vault 上验 dedup move / archive / market_intel manifest。"""
import json
from pathlib import Path
from scripts.l1_audit.apply_2a import run_2a


def _write(policies: Path, pid, title, offnum="", url="", date="2024-01-01"):
    fm = (f"---\nid: {pid}\ntitle: {title}\nofficial_number: {offnum}\n"
          f"date: {date}\nsource_url: {url}\n---\n\n正文示例。\n")
    (policies / f"{pid}.md").write_text(fm, encoding="utf-8")


def test_run_2a_moves_dedup_archives_noise_and_manifests_market_intel(tmp_path):
    vault = tmp_path / "vault"
    policies = vault / "0_raw" / "policies"
    policies.mkdir(parents=True)
    archive_dir = vault / "0_raw" / "_archive" / "policies" / "source_audit_2026-05-31"
    duplicates_dir = vault / "0_raw" / "_duplicates"

    # 真重复:同标题,keep 带文号、dup 无文号 → 应留带文号者
    _write(policies, "P_KEEP", "同一政策标题", offnum="发改〔2024〕9号", url="https://a.gov.cn/x")
    _write(policies, "P_DUP", "同一政策标题", offnum="", url="https://b.gov.cn/y")
    _write(policies, "P_NOISE", "某导航壳噪声", url="https://news.example.com/z")
    _write(policies, "P_MI", "某储能项目清单公示", url="https://c.gov.cn/m")
    _write(policies, "P_UNIQUE", "完全独立的政策", offnum="独号1", url="https://d.gov.cn/u")

    decisions = {
        "archive": ["P_NOISE"],
        "archive_reasons": {"P_NOISE": "导航壳真噪声"},
        "market_intel": [{"pid": "P_MI", "title": "某储能项目清单公示"}],
    }
    manifest = tmp_path / "out" / "market_intel_manifest.jsonl"
    log = tmp_path / "out" / "apply_log.jsonl"

    summary = run_2a(str(policies), str(archive_dir), str(duplicates_dir),
                     str(manifest), str(log), decisions, "2026-05-31")

    # dedup: P_DUP 迁走、P_KEEP 留、_duplicate_of 写对
    assert not (policies / "P_DUP.md").exists()
    assert (policies / "P_KEEP.md").exists()
    moved = duplicates_dir / "P_DUP.md"
    assert moved.exists()
    assert "_duplicate_of: P_KEEP" in moved.read_text(encoding="utf-8")

    # archive: P_NOISE 迁到 archive_dir、原位消失
    assert not (policies / "P_NOISE.md").exists()
    assert (archive_dir / "P_NOISE.md").exists()

    # market_intel: P_MI 原位不动
    assert (policies / "P_MI.md").exists()

    # 独立政策不受影响
    assert (policies / "P_UNIQUE.md").exists()

    # manifest 只 1 条(market_intel)
    mani_lines = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(mani_lines) == 1 and mani_lines[0]["pid"] == "P_MI"

    # log 含 dedup_move + archive
    log_lines = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    actions = {e["action"] for e in log_lines}
    assert actions == {"dedup_move", "archive"}

    assert summary == {"dedup_moved": 1, "archived": 1, "market_intel": 1}
