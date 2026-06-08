from scripts.l1_collect.channel_catalog import Channel, ChannelStatus


def _ch(level, domain):
    return Channel(city=("国家发改委" if level == "国家" else "广东省"),
                   province=("国家" if level == "国家" else "广东省"), level=level,
                   city_code="000000", channel_type="发改委", root_domain=domain,
                   list_url=f"https://{domain}/", source="discovery",
                   status=ChannelStatus.验证)


def test_select_channels_national_only():
    from scripts.l1_collect.run_incremental import _select_channels
    chans = [_ch("国家", "ndrc.gov.cn"), _ch("市", "gz.gov.cn")]
    out = _select_channels(chans, ["national"])
    assert len(out) == 1 and out[0].level == "国家"


def test_select_channels_province_city_excludes_national():
    from scripts.l1_collect.run_incremental import _select_channels
    chans = [_ch("国家", "ndrc.gov.cn"), _ch("省", "drc.gd.gov.cn"), _ch("市", "gz.gov.cn")]
    out = _select_channels(chans, ["province", "city"])
    assert all(c.level != "国家" for c in out) and len(out) == 2


def test_gate_extracted_routes_pass_and_reject(tmp_path):
    """gate=pass→进ingest桶;reject→进quarantine,不进ingest桶。"""
    import json
    from scripts.l1_collect.run_incremental import _gate_extracted_dir
    ext = tmp_path / "ext"; ext.mkdir()
    passed = tmp_path / "passed"; passed.mkdir()
    comm = tmp_path / "comm"
    quar = tmp_path / "q.jsonl"
    (ext / "a.json").write_text(json.dumps({
        "url": "https://ndrc.gov.cn/zcfb/d.html",
        "title": "关于充电设施的通知", "body": "根据部署,现通知如下:" + "正文" * 50}),
        encoding="utf-8")
    (ext / "b.json").write_text(json.dumps({
        "url": "https://in-en.com/x.html", "title": "市场快讯", "body": "据记者"}),
        encoding="utf-8")
    n_pass, n_comm, n_rej, n_review = _gate_extracted_dir(ext, passed, comm, quar, llm_fn=None)
    assert n_pass == 1 and n_rej == 1
    assert (passed / "a.json").exists()
    assert not (passed / "b.json").exists()
    assert quar.exists() and "in-en" in quar.read_text()


def test_gate_dir_three_way_split(tmp_path):
    import json
    from scripts.l1_collect.run_incremental import _gate_extracted_dir
    ext = tmp_path / "ext"; ext.mkdir()
    (ext / "a.json").write_text(json.dumps(
        {"url": "https://x.gov.cn/a.html", "title": "某办法的通知", "body": "现就……"}),
        encoding="utf-8")
    (ext / "b.json").write_text(json.dumps(
        {"url": "https://x.gov.cn/zcjd/b.html", "title": "《某办法》政策解读", "body": "解读"}),
        encoding="utf-8")
    passed = tmp_path / "passed"; comm = tmp_path / "comm"
    quar = tmp_path / "q.jsonl"
    n_pass, n_comm, n_rej, n_review = _gate_extracted_dir(ext, passed, comm, quar, llm_fn=None)
    assert n_pass == 1 and n_comm == 1
    assert (passed / "a.json").exists()
    assert (comm / "b.json").exists()


def test_soft_lock_noop_when_service_absent():
    """service.l1_status 不在树上 → 软锁 no-op,不报错。"""
    from scripts.l1_collect.run_incremental import _l1_lock
    with _l1_lock():
        pass  # 不抛异常即通过


def test_select_channels_channel_type_filter():
    from scripts.l1_collect.run_incremental import _select_channels
    from scripts.l1_collect.channel_catalog import Channel, ChannelStatus
    def mk(ct, lvl="省"):
        return Channel(city="x", province="p", level=lvl, city_code="320000",
                       channel_type=ct, root_domain="d", list_url="u",
                       source="s", status=ChannelStatus.验证)
    chans = [mk("发改委"), mk("商务"), mk("市监"), mk("商务部", "国家")]
    sel = _select_channels(chans, ["province", "national"], channel_types=["商务", "市监"])
    types = {c.channel_type for c in sel}
    assert types == {"商务", "市监", "商务部"}   # 子串匹配:商务部 含"商务"
    assert "发改委" not in types
