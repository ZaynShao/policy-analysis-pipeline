from __future__ import annotations
from pathlib import Path
from urllib.parse import urlparse
import yaml
from scripts.l2_attribution.models import ChannelEntry


def load_registry(path: str) -> dict:
    """读 channel_registry.yaml -> {domain: ChannelEntry}。"""
    rows = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    out = {}
    for r in rows:
        out[r["domain"]] = ChannelEntry(
            domain=r["domain"],
            issuer_short=r["issuer_short"],
            issuer_canonical=r.get("issuer_canonical", ""),
            region=r["region"],
        )
    return out


def host_of(url: str) -> str:
    if not url:
        return ""
    return (urlparse(url).netloc or "").lower()


def lookup(registry: dict, url: str):
    """url -> host -> ChannelEntry | None。"""
    return registry.get(host_of(url))
