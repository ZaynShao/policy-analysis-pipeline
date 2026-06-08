def test_should_refetch_thin_only():
    from scripts.l1_collect.pdf_refetch import _body_chars, should_refetch_text
    short = "---\npid: x\nsource_url: u\n---\n\n封面"
    rich = "---\npid: x\nsource_url: u\n---\n\n" + "正文。" * 400
    assert should_refetch_text(short) is True
    assert should_refetch_text(rich) is False


def test_monotonic_guard_blocks_shorter(tmp_path):
    """新捕获不比旧长 → 不写,返回 skipped。"""
    from scripts.l1_collect.pdf_refetch import upgrade_policy_body
    p = tmp_path / "P_x.md"
    old_body = "原始较长正文" * 100
    p.write_text(f"---\npid: P_x\nsource_url: https://x.gov.cn/d.pdf\n---\n\n{old_body}",
                 encoding="utf-8")
    res = upgrade_policy_body(p, fetch_fn=lambda url: "短")  # 比旧短
    assert res["upgraded"] is False
    assert res["reason"] == "not_longer"
    assert old_body in p.read_text(encoding="utf-8")  # 原文未动


def test_upgrade_writes_when_strictly_longer(tmp_path):
    from scripts.l1_collect.pdf_refetch import upgrade_policy_body
    p = tmp_path / "P_y.md"
    p.write_text("---\npid: P_y\nsource_url: https://x.gov.cn/d.pdf\n---\n\n封面",
                 encoding="utf-8")
    new = "第一条 本办法适用于...。" * 80
    res = upgrade_policy_body(p, fetch_fn=lambda url: new)
    assert res["upgraded"] is True
    assert res["new_chars"] > res["old_chars"]
    content = p.read_text(encoding="utf-8")
    assert "第一条" in content
    assert "source_url: https://x.gov.cn/d.pdf" in content  # frontmatter 不动


def test_skip_when_no_source_url(tmp_path):
    from scripts.l1_collect.pdf_refetch import upgrade_policy_body
    p = tmp_path / "P_z.md"
    p.write_text("---\npid: P_z\n---\n\n封面", encoding="utf-8")
    res = upgrade_policy_body(p, fetch_fn=lambda url: "x" * 9999)
    assert res["upgraded"] is False and res["reason"] == "no_source_url"
