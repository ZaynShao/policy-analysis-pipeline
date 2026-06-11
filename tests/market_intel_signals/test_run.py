import json

from scripts.market_intel_signals.run import main, run_dryrun


def test_dryrun_writes_state_and_html_without_modifying_vault(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    policies = vault / "0_raw" / "policies"
    meta = vault / "_meta"
    policies.mkdir(parents=True)
    meta.mkdir(parents=True)
    (meta / "themes_registry.yaml").write_text(
        "themes:\n"
        "  - id: v2g\n"
        "    zh: V2G\n"
        "    aliases: [V2G, 车网互动]\n",
        encoding="utf-8",
    )
    raw = policies / "p.md"
    raw.write_text(
        "---\n"
        "id: P_NEW\n"
        "aliases: [P_OLD]\n"
        "title: 南方电网首个交流V2G落地海口\n"
        "date: '2025-12-27'\n"
        "region: {level: 市, code: '460100', name: 海口市}\n"
        "---\n"
        "车网互动项目正式投运。",
        encoding="utf-8",
    )
    manifest = state / "source_ready" / "market_intel_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"pid": "P_OLD", "class": "market_intel"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    before = raw.read_text(encoding="utf-8")

    result = run_dryrun(vault, manifest, state / "market")

    assert result["summary"]["emitted_signals"] == 1
    assert raw.read_text(encoding="utf-8") == before
    assert (state / "market" / "market_signals.jsonl").exists()
    assert (state / "market" / "review_queue.jsonl").exists()
    assert (state / "market" / "summary.json").exists()
    assert (state / "market" / "reports" / "market_intel_signals_dryrun.html").exists()
    html = (state / "market" / "reports" / "market_intel_signals_dryrun.html").read_text(encoding="utf-8")
    assert "市场情报信号 dry-run" in html
    assert "内部验证" in html


def test_dryrun_queues_missing_pid(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    (vault / "0_raw" / "policies").mkdir(parents=True)
    (vault / "_meta").mkdir(parents=True)
    (vault / "_meta" / "themes_registry.yaml").write_text("themes: []\n", encoding="utf-8")
    manifest = state / "source_ready" / "market_intel_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"pid": "P_MISSING", "class": "market_intel"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = run_dryrun(vault, manifest, state / "market")

    assert result["summary"]["emitted_signals"] == 0
    assert result["summary"]["review_queue"] == 1
    row = json.loads((state / "market" / "review_queue.jsonl").read_text(encoding="utf-8").strip())
    assert row["reason"] == "manifest_pid_not_found"


def test_cli_dryrun_uses_default_manifest_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "vault"
    state = tmp_path / "state_out"
    policies = vault / "0_raw" / "policies"
    policies.mkdir(parents=True)
    (vault / "_meta").mkdir(parents=True)
    (vault / "_meta" / "themes_registry.yaml").write_text("themes: []\n", encoding="utf-8")
    (policies / "p.md").write_text(
        "---\n"
        "id: P_DEFAULT_MANIFEST\n"
        "title: 默认 manifest 政策\n"
        "date: '2026-06-01'\n"
        "region: {level: 国家, code: '000000', name: 全国}\n"
        "---\n"
        "正文\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "state" / "source_ready" / "market_intel_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"pid": "P_DEFAULT_MANIFEST", "class": "market_intel"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert main(["dry-run", "--vault", str(vault), "--state", str(state)]) == 0
    assert json.loads((state / "summary.json").read_text(encoding="utf-8"))["manifest_rows"] == 1
