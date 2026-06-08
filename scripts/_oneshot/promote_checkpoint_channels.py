"""SW11 CHECKPOINT 决议:把用户人工核过的 8 个真商务/市监站 候选→验证。
这是 CHECKPOINT 人工裁决的一次性钉快照(非常驻规则):标记法太窄漏判的真站,
经用户眼过(host 匹配机构+省+口径)确认后提升,进 SW12 backfill。
"""
from __future__ import annotations
from pathlib import Path

from scripts.l1_collect.channel_catalog import load_catalog, save_catalog, ChannelStatus

CAT = Path("state/T1_channels/channel_catalog.yaml")

# 用户 CHECKPOINT 确认的 8 个真站(by root_domain)
CONFIRMED = {
    "dgboc.dg.gov.cn",          # 东莞市商务局
    "sw.beijing.gov.cn",        # 北京市商务局
    "shangwuju.tj.gov.cn",      # 天津市商务局
    "zcom.zj.gov.cn",           # 浙江省商务厅
    "sxdofcom.shaanxi.gov.cn",  # 陕西省商务厅
    "scjg.gansu.gov.cn",        # 甘肃省市场监督管理局
    "amr.hlj.gov.cn",           # 黑龙江省市场监督管理局
    "scjdglj.gxzf.gov.cn",      # 广西市场监督管理局
}


NOTE = "checkpoint-promoted-2026-06-08"


def main() -> None:
    chans = load_catalog(CAT)
    promoted, touched = [], []
    for c in chans:
        if c.root_domain in CONFIRMED and c.channel_type in ("商务", "市监"):
            if c.status == ChannelStatus.候选:
                c.status = ChannelStatus.验证
                promoted.append(c)
            if NOTE not in (c.notes or ""):     # 幂等:provenance 落数据(人工策展审计痕)
                c.notes = f"{c.notes}; {NOTE}" if c.notes else NOTE
            touched.append(c)
    save_catalog(chans, CAT)
    print(f"提升 {len(promoted)} 候选→验证 | 打 provenance {len(touched)}/{len(CONFIRMED)}:")
    for c in touched:
        print(f"  {c.channel_type} {c.city:14s} {c.root_domain:26s} status={c.status.value}")
    missing = CONFIRMED - {c.root_domain for c in touched}
    if missing:
        print(f"⚠ 不在表:{missing}")
    ver = [c for c in chans if c.channel_type in ("商务", "市监")
           and c.status == ChannelStatus.验证]
    print(f"商务/市监 验证总数(进 backfill):{len(ver)}")


if __name__ == "__main__":
    main()
