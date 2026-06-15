def test_targets_for_levels_merges_province_energy_without_losing_known_domain(monkeypatch):
    from scripts._oneshot import expand_channels_l1 as mod

    registry_target = {
        "city": "山东省",
        "province": "山东省",
        "level": "省",
        "city_code": "370000",
        "channel_type": "能源局",
        "root_domain": "nyj.shandong.gov.cn",
    }
    energy_targets = [
        {
            "city": "山东省",
            "province": "山东省",
            "level": "省",
            "city_code": "370000",
            "channel_type": "能源局",
            "root_domain": None,
        },
        {
            "city": "山东省",
            "province": "山东省",
            "level": "省",
            "city_code": "370000",
            "channel_type": "发改委",
            "root_domain": None,
        },
    ]
    monkeypatch.setattr(mod, "province_targets_from_registry", lambda reg: [registry_target])
    monkeypatch.setattr(mod, "province_energy_targets", lambda: energy_targets)
    monkeypatch.setattr(mod, "nea_regulatory_targets", lambda: [{"city": "国家能源局华北能源监管局"}])

    targets = mod.targets_for_levels(["province", "nea_regulatory"])

    by_key = {(t["province"], t["channel_type"]): t for t in targets if "province" in t}
    assert by_key[("山东省", "能源局")]["root_domain"] == "nyj.shandong.gov.cn"
    assert by_key[("山东省", "发改委")]["root_domain"] is None
    assert {"city": "国家能源局华北能源监管局"} in targets
