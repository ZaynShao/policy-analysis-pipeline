"""依 city_priority 算分 + 渠道有效性,生成 city_priority.yaml(P0/P1/P2 三档)。

P0 = 业务驱动 union(~45 城)且 channel_catalog 至少有 1 个 status=验证 的渠道
P1 = 京沪津渝下辖区(本任务暂留 placeholder,需要单独 admin codes 数据)
P2 = 全市级 - P0
"""
from __future__ import annotations
import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.l1_collect.channel_catalog import load_catalog, ChannelStatus
from scripts.l1_collect.city_priority import all_p0_cities

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "state" / "T1_channels" / "channel_catalog.yaml"
OUT = ROOT / "state" / "T1_channels" / "city_priority.yaml"


def main() -> None:
    catalog = load_catalog(CATALOG)
    by_city = {}
    for c in catalog:
        by_city.setdefault(c.city, []).append(c)
    verified_cities = {
        city: sum(1 for c in chs if c.status == ChannelStatus.验证)
        for city, chs in by_city.items()
    }
    p0 = []
    for c, r, s in all_p0_cities():
        p0.append({
            "city": c,
            "reasons": r,
            "priority_score": s,
            "verified_channels": verified_cities.get(c, 0),
        })
    p2 = []
    for city in sorted(by_city.keys()):
        if city not in {x["city"] for x in p0}:
            p2.append({"city": city, "verified_channels": verified_cities.get(city, 0)})
    out = {
        "version": "2026-05-19",
        "batches": {"P0": p0, "P1": [], "P2": p2},
        "notes": "P1 待 admin codes 补京沪津渝下辖区数据后填",
    }
    OUT.write_text(yaml.dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"P0 = {len(p0)} cities | P2 = {len(p2)} cities | P1 = 0 (placeholder)")
    print(f"saved to {OUT}")


if __name__ == "__main__":
    main()
