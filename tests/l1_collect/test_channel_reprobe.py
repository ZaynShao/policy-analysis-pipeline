from scripts.l1_collect.channel_catalog import Channel, ChannelStatus


def _channel(**overrides):
    data = {
        "city": "山东省",
        "province": "山东省",
        "level": "省",
        "city_code": "370000",
        "channel_type": "能源局",
        "root_domain": "nyj.shandong.gov.cn",
        "list_url": "https://nyj.shandong.gov.cn/old/",
        "source": "discovery",
        "status": ChannelStatus.候选,
        "last_probed_at": "2026-06-01T00:00:00Z",
        "probe_result": "http_error",
        "notes": "",
    }
    data.update(overrides)
    return Channel(**data)


def test_reprobe_candidate_promotes_when_discover_verifies(monkeypatch):
    from scripts.l1_collect import channel_reprobe as cr

    ch = _channel(notes="seed")
    fresh = _channel(
        status=ChannelStatus.验证,
        root_domain="nyj.shandong.gov.cn",
        list_url="https://nyj.shandong.gov.cn/col/policy/",
        last_probed_at="2026-06-15T01:00:00Z",
        probe_result="ok",
    )
    monkeypatch.setattr(cr, "discover_one", lambda target: fresh)

    updated, outcome = cr.reprobe_candidate(ch, today="2026-06-15")

    assert updated is ch
    assert outcome == "promoted"
    assert ch.status == ChannelStatus.验证
    assert ch.list_url == "https://nyj.shandong.gov.cn/col/policy/"
    assert ch.probe_result == "ok"
    assert "auto-promoted-2026-06-15-probe-ok" in ch.notes


def test_reprobe_candidate_probe_ok_but_ambiguous_goes_to_review_pool(monkeypatch):
    from scripts.l1_collect import channel_reprobe as cr

    ch = _channel()
    fresh = _channel(status=ChannelStatus.候选, probe_result="ok")
    appended = []
    monkeypatch.setattr(cr, "discover_one", lambda target: fresh)
    monkeypatch.setattr(cr.review_pool, "append", lambda entry: appended.append(entry))
    monkeypatch.setattr(cr.review_pool, "candidate_entry", lambda channel: {"ref": channel.root_domain})

    _, outcome = cr.reprobe_candidate(ch, today="2026-06-15")

    assert outcome == "ambiguous"
    assert ch.status == ChannelStatus.候选
    assert appended == [{"ref": "nyj.shandong.gov.cn"}]


def test_reprobe_candidate_keeps_http_error_candidate_out_of_pool(monkeypatch):
    from scripts.l1_collect import channel_reprobe as cr

    ch = _channel()
    fresh = _channel(
        status=ChannelStatus.候选,
        last_probed_at="2026-06-15T01:00:00Z",
        probe_result="http_error",
    )
    appended = []
    monkeypatch.setattr(cr, "discover_one", lambda target: fresh)
    monkeypatch.setattr(cr.review_pool, "append", lambda entry: appended.append(entry))

    _, outcome = cr.reprobe_candidate(ch, today="2026-06-15")

    assert outcome == "still_candidate"
    assert ch.status == ChannelStatus.候选
    assert ch.last_probed_at == "2026-06-15T01:00:00Z"
    assert ch.probe_result == "http_error"
    assert appended == []


def test_reprobe_candidates_respects_dry_run_save_gate(monkeypatch):
    from scripts.l1_collect import channel_reprobe as cr

    catalog = [_channel(), _channel(city="江苏省", province="江苏省", city_code="320000")]
    monkeypatch.setattr(cr, "reprobe_candidate", lambda ch, today: (ch, "still_candidate"))
    saved = []
    monkeypatch.setattr(cr, "save_catalog", lambda catalog_arg, path: saved.append((catalog_arg, path)))

    assert cr.reprobe_candidates(catalog, today="2026-06-15", dry_run=True)["scanned"] == 2
    assert saved == []

    assert cr.reprobe_candidates(catalog, today="2026-06-15", dry_run=False)["scanned"] == 2
    assert len(saved) == 1


def test_reprobe_candidates_filters_only_types_and_limit(monkeypatch):
    from scripts.l1_collect import channel_reprobe as cr

    catalog = [
        _channel(channel_type="能源局"),
        _channel(channel_type="发改委", city="江苏省", province="江苏省", city_code="320000"),
        _channel(channel_type="商务", city="广东省", province="广东省", city_code="440000"),
    ]
    outcomes = iter(["promoted", "ambiguous"])
    seen = []

    def fake_reprobe(ch, today):
        seen.append(ch.channel_type)
        return ch, next(outcomes)

    monkeypatch.setattr(cr, "reprobe_candidate", fake_reprobe)

    stats = cr.reprobe_candidates(
        catalog,
        only_types={"能源局", "发改委"},
        limit=2,
        dry_run=True,
        today="2026-06-15",
    )

    assert seen == ["能源局", "发改委"]
    assert stats == {"scanned": 2, "promoted": 1, "ambiguous": 1}


def test_stamp_is_idempotent():
    from scripts.l1_collect.channel_reprobe import _stamp

    ch = _channel(notes="seed")
    _stamp(ch, "auto-promoted-2026-06-15-probe-ok")
    _stamp(ch, "auto-promoted-2026-06-15-probe-ok")

    assert ch.notes.count("auto-promoted-2026-06-15-probe-ok") == 1
