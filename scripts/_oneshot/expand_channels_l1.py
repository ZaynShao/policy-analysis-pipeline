"""L1 渠道发现:fresh discover_one(Tavily搜→LLM选列表页→probe验证) → add-if-absent 进 catalog。

DISCOVER_LEVELS=national（默认，Task10 国家级切片） | national,province（Task11 backfill 前）。
city 级不在此（784 大表已是市级候选，Task11 用 probe 提升候选→验证，另脚本）。
非破坏 + 幂等：已在 catalog 的域名跳过；国家/省域名不在市级大表 → 首跑全部新增。
需 env：TAVILY_API_KEY + OPENAI_BASE_URL/OPENAI_API_KEY（deepseek 供 LLM 选 URL）。
"""
from __future__ import annotations
import os
from pathlib import Path

from collections import Counter

from scripts.l1_collect.channel_discovery import (
    NATIONAL_TARGETS, province_targets_from_registry, commerce_market_targets, discover_one)
from scripts.l1_collect.channel_catalog import load_catalog, save_catalog, ChannelStatus

CAT = Path("state/T1_channels/channel_catalog.yaml")
REG = Path.home() / "Documents/Zayn Main/政策分析/_meta/channel_registry.yaml"
LEVEL_CN = {"national": "国家", "province": "省"}


def main() -> None:
    levels = [l.strip() for l in os.environ.get("DISCOVER_LEVELS", "national").split(",") if l.strip()]
    targets = []
    if "national" in levels:
        targets += NATIONAL_TARGETS
    if "province" in levels:
        targets += province_targets_from_registry(REG)
    if "commerce_market" in levels:
        targets += commerce_market_targets(registry_path=REG)

    existing = load_catalog(CAT) if CAT.exists() else []
    have = {c.root_domain for c in existing}

    discovered = []
    for t in targets:
        if t["root_domain"] in have:
            continue
        ch = discover_one(t)
        if not ch:
            continue
        have.add(ch.root_domain)
        discovered.append(ch)
        print(f"  {ch.level:4s} {ch.status.value:3s} {ch.root_domain:26s} {ch.list_url}")

    save_catalog(existing + discovered, CAT)
    print("=" * 56)
    v = sum(1 for c in discovered if c.status == ChannelStatus.验证)
    print(f"新增 {len(discovered)} | 验证 {v} 候选 {len(discovered) - v}")
    for (ct, st), n in sorted(Counter((c.channel_type, c.status.value) for c in discovered).items()):
        print(f"  {ct:8s} {st:3s} {n}")


if __name__ == "__main__":
    main()
