import json
from pathlib import Path
import scripts.l1_collect.step4_fetch as s4


class _Res:
    def __init__(self, via, body=""):
        self.via = via; self.body = body


def test_fetch_retries_once_then_succeeds(tmp_path, monkeypatch):
    calls = {"n": 0}
    def fake_fetch(url):
        calls["n"] += 1
        return _Res("fetch_error") if calls["n"] == 1 else _Res("firecrawl", "正文够长")
    monkeypatch.setattr(s4, "fetch_article", fake_fetch)
    inp = tmp_path / "cand.jsonl"
    inp.write_text(json.dumps({"url": "http://x.gov.cn/a", "title": "t"}) + "\n", encoding="utf-8")
    success, error = s4.fetch_candidates(inp, tmp_path / "fetch", tmp_path / "ferr.txt")
    assert calls["n"] == 2 and success == 1 and error == 0


def test_fetch_title_with_nel_not_oversplit(tmp_path, monkeypatch):
    # title 含 U+0085(NEL):json.dumps(ensure_ascii=False) 原样写出该字符,
    # splitlines() 会在 NEL 处把一行 JSON 拆成两半 → json.loads 崩/丢候选。
    # 读取须用 split("\n"),让它仍是 1 条候选。
    calls = {"n": 0}
    def fake_fetch(url):
        calls["n"] += 1
        return _Res("firecrawl", "正文够长")
    monkeypatch.setattr(s4, "fetch_article", fake_fetch)
    inp = tmp_path / "cand.jsonl"
    title = "节能\u0085补贴通知"  # NEL 嵌在标题中
    inp.write_text(
        json.dumps({"url": "http://x.gov.cn/a", "title": title}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    success, error = s4.fetch_candidates(inp, tmp_path / "fetch", tmp_path / "ferr.txt")
    assert calls["n"] == 1 and success == 1 and error == 0


def test_fetch_still_fails_after_retry_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(s4, "fetch_article", lambda url: _Res("fetch_error"))
    inp = tmp_path / "cand.jsonl"
    inp.write_text(json.dumps({"url": "http://x.gov.cn/a", "title": "t"}) + "\n", encoding="utf-8")
    success, error = s4.fetch_candidates(inp, tmp_path / "fetch", tmp_path / "ferr.txt")
    assert success == 0 and error == 1
    assert (tmp_path / "ferr.txt").read_text(encoding="utf-8").strip() == "http://x.gov.cn/a"
