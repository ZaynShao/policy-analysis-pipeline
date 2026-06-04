import json
import subprocess

from scripts.analysis_high_precision_relations.run import run_preview


def _write_policy(path, policy_id, *, title="政策标题", official_number="", body="正文", aliases=None):
    aliases = aliases or []
    path.parent.mkdir(parents=True, exist_ok=True)
    alias_lines = "\n".join(f"  - {alias}" for alias in aliases)
    aliases_block = f"aliases:\n{alias_lines}\n" if aliases else "aliases: []\n"
    path.write_text(
        "---\n"
        f"id: {policy_id}\n"
        f"{aliases_block}"
        f"title: {title}\n"
        f"official_number: {official_number}\n"
        "---\n"
        f"## 政策原文\n\n{body}",
        encoding="utf-8",
    )


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def test_preview_emits_reference_and_basis_from_tracked_raw_only(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    vault.mkdir()
    _init_git_repo(vault)
    _write_policy(
        vault / "0_raw" / "policies" / "target.md",
        "P_2025_NDRC_357_a",
        title="关于加快推进虚拟电厂发展的指导意见",
        official_number="发改能源〔2025〕357号",
        body="目标政策正文",
    )
    _write_policy(
        vault / "0_raw" / "policies" / "source.md",
        "P_2026_SD_001",
        title="山东省虚拟电厂管理办法",
        official_number="鲁发改能源〔2026〕1号",
        body="根据《国家发展改革委 国家能源局关于加快推进虚拟电厂发展的指导意见》（发改能源〔2025〕357号），结合实际制定本办法。",
    )
    _write_policy(
        vault / "0_raw" / "policies" / "untracked.md",
        "P_2026_UNTRACKED",
        official_number="未跟踪〔2026〕9号",
        body="不应进入索引。",
    )
    subprocess.run(["git", "add", "0_raw/policies/target.md", "0_raw/policies/source.md"], cwd=vault, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=vault, check=True, stdout=subprocess.DEVNULL)

    result = run_preview(vault, state)

    summary = result["summary"]
    assert summary["tracked_policy_count"] == 2
    assert summary["untracked_policy_count"] == 1
    rows = _read_jsonl(state / "high_precision_relation_candidates.jsonl")
    rels = {(row["from"], row["to"], row["rel"]) for row in rows}
    assert ("P_2026_SD_001", "P_2025_NDRC_357_a", "references") in rels
    assert ("P_2026_SD_001", "P_2025_NDRC_357_a", "cites_basis") in rels
    assert all(row["to"] != "P_2026_UNTRACKED" for row in rows)

    html = (state / "reports" / "high_precision_relation_preview.html").read_text(encoding="utf-8")
    assert "不写资料库" in html
    assert "不调用模型" in html


def test_preview_emits_supersedes_and_clarifies(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    vault.mkdir()
    _init_git_repo(vault)
    _write_policy(
        vault / "0_raw" / "policies" / "old_rule.md",
        "P_2020_NDRC_889",
        title="电力中长期交易基本规则",
        official_number="发改能源规〔2020〕889号",
    )
    _write_policy(
        vault / "0_raw" / "policies" / "new_rule.md",
        "P_2025_NDRC_1656_a",
        title="电力中长期交易基本规则",
        official_number="发改能源规〔2025〕1656号",
        body="本规则自发布之日起施行。《电力中长期交易基本规则》（发改能源规〔2020〕889号）同时废止。",
    )
    _write_policy(
        vault / "0_raw" / "policies" / "base.md",
        "P_2024_MOFCOM_75_b",
        title="汽车以旧换新补贴实施细则",
        official_number="商消费函〔2024〕75号",
    )
    _write_policy(
        vault / "0_raw" / "policies" / "clarify.md",
        "P_2024_BJ_05312f8b",
        title="北京市汽车以旧换新补贴实施细则",
        official_number="京商消费〔2024〕5号",
        body="按照《汽车以旧换新补贴实施细则》（商消费函〔2024〕75号）要求，制定本实施细则。",
    )
    subprocess.run(["git", "add", "."], cwd=vault, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=vault, check=True, stdout=subprocess.DEVNULL)

    run_preview(vault, state)

    rows = _read_jsonl(state / "high_precision_relation_candidates.jsonl")
    rels = {(row["from"], row["to"], row["rel"]) for row in rows}
    assert ("P_2025_NDRC_1656_a", "P_2020_NDRC_889", "supersedes") in rels
    assert ("P_2024_BJ_05312f8b", "P_2024_MOFCOM_75_b", "clarifies") in rels
    supersedes = next(row for row in rows if row["rel"] == "supersedes")
    assert "同时废止" in supersedes["evidence"]

    summary = json.loads((state / "high_precision_relation_summary.json").read_text(encoding="utf-8"))
    assert summary["rows_by_relation"]["supersedes"] == 1
    assert summary["rows_by_relation"]["clarifies"] == 1
    for rel in ["references", "cites_basis", "supersedes", "clarifies"]:
        assert (state / "policy_relation_candidates" / f"{rel}.jsonl").exists()
