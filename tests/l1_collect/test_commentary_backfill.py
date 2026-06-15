from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.l1_collect.dedup import DedupIndex


def _commentary(text: str, business_tag: str = "power") -> str:
    return f"""---
title: 测试评论
business_tag: {business_tag}
---
{text}
"""


def test_extract_policy_refs_finds_title_and_gov_url_with_context_and_tag():
    from scripts.l1_collect.commentary_backfill import extract_policy_refs

    md = _commentary(
        "评论提到《山东省光伏发电实施意见》需要关注。"
        "原文链接 https://fgw.shandong.gov.cn/art/2026/1/1/art_1_2.html ，"
        "该电力政策影响明显。"
    )

    refs = extract_policy_refs(md, source="c1.md")

    assert len(refs) == 2
    titles = {r.title for r in refs}
    urls = {r.url for r in refs}
    assert "山东省光伏发电实施意见" in titles
    assert "https://fgw.shandong.gov.cn/art/2026/1/1/art_1_2.html" in urls
    assert {r.business_tag for r in refs} == {"power"}
    assert {r.source_commentary for r in refs} == {"c1.md"}
    assert all("电力" in r.context or "光伏" in r.context for r in refs)


def test_extract_policy_refs_finds_policy_title_from_frontmatter_title():
    from scripts.l1_collect.commentary_backfill import extract_policy_refs

    md = """---
title: 解读《关于推进新型储能发展的通知》
business_tag: power
---
正文只讨论新型储能发展影响,没有重复政策全称。
"""

    refs = extract_policy_refs(md, source="title.md")

    assert len(refs) == 1
    assert refs[0].title == "关于推进新型储能发展的通知"
    assert refs[0].context == "解读《关于推进新型储能发展的通知》"


def test_extract_policy_refs_dedups_same_policy_title_from_frontmatter_and_body():
    from scripts.l1_collect.commentary_backfill import extract_policy_refs

    md = """---
title: 解读《关于推进新型储能发展的通知》
business_tag: power
---
正文再次提到《关于推进新型储能发展的通知》。
"""

    refs = extract_policy_refs(md, source="dup.md")

    assert [r.title for r in refs] == ["关于推进新型储能发展的通知"]


def test_is_in_scope_blocks_finance_title_and_accepts_energy_terms():
    from scripts.l1_collect.commentary_backfill import PolicyRef, is_in_scope

    finance = PolicyRef(
        title="关于深化上海全球资产管理中心建设的若干意见",
        url=None,
        source_commentary="finance.md",
        business_tag="cross",
        context="关于深化上海全球资产管理中心建设的若干意见",
    )
    energy = PolicyRef(
        title="关于推进光伏发电和充电设施建设的通知",
        url=None,
        source_commentary="energy.md",
        business_tag="charging",
        context="新能源 电力 充电",
    )

    assert is_in_scope(finance) is False
    assert is_in_scope(energy) is True


def test_is_already_collected_checks_url_and_title_index():
    from scripts.l1_collect.commentary_backfill import PolicyRef, is_already_collected

    dedup = DedupIndex()
    dedup.add(url="https://fgw.example.gov.cn/a.html", official_number="", title="")
    title_index = [("山东省光伏发电实施意见", "pid-1", "山东省光伏发电实施意见")]

    assert is_already_collected(
        PolicyRef(None, "https://fgw.example.gov.cn/a.html", "c.md", "power", ""),
        dedup,
        title_index,
    )
    assert is_already_collected(
        PolicyRef("山东省光伏发电实施意见", None, "c.md", "power", ""),
        DedupIndex(),
        title_index,
    )
    assert not is_already_collected(
        PolicyRef("新的电力政策", "https://fgw.example.gov.cn/new.html", "c.md", "power", ""),
        DedupIndex(),
        [],
    )


def test_find_backfill_candidates_filters_collected_irrelevant_and_dedups(tmp_path):
    from scripts.l1_collect.commentary_backfill import find_backfill_candidates

    commentaries = tmp_path / "commentaries"
    commentaries.mkdir()
    (commentaries / "collected.md").write_text(
        _commentary("已采链接 https://fgw.example.gov.cn/old.html 涉及电力。"),
        encoding="utf-8",
    )
    (commentaries / "finance.md").write_text(
        _commentary("提到《关于深化上海全球资产管理中心建设的若干意见》。", "cross"),
        encoding="utf-8",
    )
    (commentaries / "energy1.md").write_text(
        _commentary("新政策《关于推进新型储能发展的通知》值得关注。"),
        encoding="utf-8",
    )
    (commentaries / "energy2.md").write_text(
        _commentary("重复提到《关于推进新型储能发展的通知》。"),
        encoding="utf-8",
    )
    dedup = DedupIndex()
    dedup.add(url="https://fgw.example.gov.cn/old.html", official_number="", title="")

    refs = find_backfill_candidates(commentaries, dedup, [])

    assert len(refs) == 1
    assert refs[0].title == "关于推进新型储能发展的通知"


def test_run_backfill_dry_run_writes_candidates_without_fetch_or_ingest(tmp_path, monkeypatch):
    from scripts.l1_collect import commentary_backfill as cb

    commentaries = tmp_path / "commentaries"
    policies = tmp_path / "policies"
    state = tmp_path / "state"
    commentaries.mkdir()
    policies.mkdir()
    (commentaries / "c.md").write_text(
        _commentary("新链接 https://fgw.example.gov.cn/new.html 与电力有关。"),
        encoding="utf-8",
    )
    called = {"fetch": False, "ingest": False}
    monkeypatch.setattr(cb.step4_fetch, "fetch_candidates", lambda *a, **k: called.__setitem__("fetch", True))
    monkeypatch.setattr(cb.step5_ingest, "ingest_extracted", lambda *a, **k: called.__setitem__("ingest", True))

    stats = cb.run_backfill(commentaries, policies, dry_run=True, state_dir=state)

    out = state / "l1_backfill" / "from_commentary.jsonl"
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert stats["scanned_commentaries"] == 1
    assert stats["candidates"] == 1
    assert rows[0]["url"] == "https://fgw.example.gov.cn/new.html"
    assert called == {"fetch": False, "ingest": False}


def test_run_backfill_apply_fetches_gates_ingests_urls_and_queues_title_only(tmp_path, monkeypatch):
    from scripts.l1_collect import commentary_backfill as cb

    url_ref = cb.PolicyRef(None, "https://fgw.example.gov.cn/new.html", "u.md", "power", "电力")
    title_ref = cb.PolicyRef("关于推进新型储能发展的通知", None, "t.md", "power", "储能")
    calls = {"fetch": 0, "extract": 0, "ingest": [], "review": []}

    monkeypatch.setattr(cb.DedupIndex, "from_vault_policies", classmethod(lambda cls, p: DedupIndex()))
    monkeypatch.setattr(cb, "build_title_index", lambda skip_paths, vault_root: [])
    monkeypatch.setattr(cb, "find_backfill_candidates", lambda *a: [url_ref, title_ref])

    def fake_fetch(cand_file: Path, fetch_dir: Path, err_log: Path):
        calls["fetch"] += 1
        fetch_dir.mkdir(parents=True)
        (fetch_dir / "f.json").write_text(
            json.dumps({
                "url": "https://fgw.example.gov.cn/new.html",
                "title": "关于电力市场建设的通知",
                "body": "现通知如下，推进电力市场建设。",
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        err_log.write_text("", encoding="utf-8")
        return 1, 0

    def fake_extract(fetch_dir: Path, ext_dir: Path, quarantine: Path):
        calls["extract"] += 1
        ext_dir.mkdir(parents=True)
        (ext_dir / "f.json").write_text((fetch_dir / "f.json").read_text(encoding="utf-8"), encoding="utf-8")
        quarantine.write_text("", encoding="utf-8")
        return 1, 0

    monkeypatch.setattr(cb.step4_fetch, "fetch_candidates", fake_fetch)
    monkeypatch.setattr(cb.step4_5_extract, "extract_all", fake_extract)
    monkeypatch.setattr(cb, "gate_one", lambda *a, **k: SimpleNamespace(action="pass"))
    monkeypatch.setattr(
        cb.step5_ingest,
        "ingest_extracted",
        lambda ext_dir, log, out_dir=None: calls["ingest"].append((ext_dir, log, out_dir)) or (1, 0, ["pid1"]),
    )
    monkeypatch.setattr(cb.review_pool, "append", lambda entry: calls["review"].append(entry) or True)

    stats = cb.run_backfill(tmp_path / "commentaries", tmp_path / "policies", dry_run=False, state_dir=tmp_path / "state")

    assert calls["fetch"] == 1
    assert calls["extract"] == 1
    assert len(calls["ingest"]) == 1
    assert calls["ingest"][0][2] == tmp_path / "policies"
    assert calls["review"][0]["kind"] == "reverse_discovery"
    assert calls["review"][0]["suggested_action"] == "collect"
    assert stats["url_collected"] == 1
    assert stats["queued_title_only"] == 1


def test_run_backfill_apply_does_not_ingest_rejected_or_irrelevant_fetched_title(tmp_path, monkeypatch):
    from scripts.l1_collect import commentary_backfill as cb

    ref = cb.PolicyRef(None, "https://fgw.example.gov.cn/new.html", "u.md", "power", "电力")
    ingested = []

    monkeypatch.setattr(cb.DedupIndex, "from_vault_policies", classmethod(lambda cls, p: DedupIndex()))
    monkeypatch.setattr(cb, "build_title_index", lambda skip_paths, vault_root: [])
    monkeypatch.setattr(cb, "find_backfill_candidates", lambda *a: [ref])

    def fake_fetch(cand_file: Path, fetch_dir: Path, err_log: Path):
        fetch_dir.mkdir(parents=True)
        (fetch_dir / "f.json").write_text(
            json.dumps({
                "url": "https://fgw.example.gov.cn/new.html",
                "title": "关于深化上海全球资产管理中心建设的若干意见",
                "body": "资产管理中心建设。",
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        err_log.write_text("", encoding="utf-8")
        return 1, 0

    monkeypatch.setattr(cb.step4_fetch, "fetch_candidates", fake_fetch)
    monkeypatch.setattr(cb.step4_5_extract, "extract_all", lambda fetch_dir, ext_dir, quarantine: (0, 0))
    monkeypatch.setattr(cb, "gate_one", lambda *a, **k: SimpleNamespace(action="pass"))
    monkeypatch.setattr(cb.step5_ingest, "ingest_extracted", lambda *a, **k: ingested.append(True))

    stats = cb.run_backfill(tmp_path / "commentaries", tmp_path / "policies", dry_run=False, state_dir=tmp_path / "state")

    assert ingested == []
    assert stats["url_collected"] == 0


def test_review_pool_declares_reverse_discovery_verdicts():
    from scripts.l1_collect import review_pool

    assert review_pool.VERDICTS["reverse_discovery"] == ("collect", "drop")
