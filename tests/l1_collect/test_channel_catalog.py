"""Tests for channel_catalog: data model + YAML IO."""
from __future__ import annotations
from pathlib import Path

from scripts.l1_collect.channel_catalog import (
    Channel, ChannelStatus, load_catalog, save_catalog,
)


def test_channel_required_fields():
    ch = Channel(
        city="杭州市", province="浙江省", level="市", city_code="330100",
        channel_type="发改委", root_domain="fgw.hangzhou.gov.cn",
        list_url="https://fgw.hangzhou.gov.cn/col/col1229453592/index.html",
        source="vault_catalog", status=ChannelStatus.候选,
    )
    assert ch.city == "杭州市"
    assert ch.status == ChannelStatus.候选


def test_channel_status_enum():
    assert {s.value for s in ChannelStatus} == {"候选", "验证", "已扫"}


def test_load_save_roundtrip(tmp_state_dir: Path, sample_catalog_yaml: str):
    p = tmp_state_dir / "T1_channels" / "channel_catalog.yaml"
    p.write_text(sample_catalog_yaml, encoding="utf-8")
    catalog = load_catalog(p)
    assert len(catalog) == 1
    assert catalog[0].city == "杭州市"
    assert catalog[0].status == ChannelStatus.验证
    out = tmp_state_dir / "T1_channels" / "out.yaml"
    save_catalog(catalog, out)
    catalog2 = load_catalog(out)
    assert catalog2[0].city == catalog[0].city


def test_save_preserves_field_order(tmp_state_dir: Path, sample_catalog_yaml: str):
    """YAML 输出字段顺序应固定,便于 diff。"""
    p = tmp_state_dir / "T1_channels" / "channel_catalog.yaml"
    p.write_text(sample_catalog_yaml, encoding="utf-8")
    catalog = load_catalog(p)
    out = tmp_state_dir / "out.yaml"
    save_catalog(catalog, out)
    text = out.read_text(encoding="utf-8")
    assert text.index("city:") < text.index("channel_type:")
