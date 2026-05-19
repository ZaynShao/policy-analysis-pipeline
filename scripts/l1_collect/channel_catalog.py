"""Channel catalog 数据模型 + YAML IO。

每个 Channel 表示一个市级政策发布渠道(发改委/能源局/政府网 等的根域名 +
列表页 URL),用 status 三态(候选/验证/已扫)跟踪流水线进度。
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Optional
import yaml


class ChannelStatus(str, Enum):
    候选 = "候选"
    验证 = "验证"
    已扫 = "已扫"


@dataclass
class Channel:
    city: str
    province: str
    level: str               # 市 / 区
    city_code: str           # 国标 6 位
    channel_type: str        # 发改委 / 能源局 / 政府网 / 经信委 / 商务局
    root_domain: str
    list_url: str
    source: str              # vault_catalog | llm_generated | manual
    status: ChannelStatus
    last_probed_at: Optional[str] = None
    probe_result: Optional[str] = None  # ok | http_error | structure_unknown | empty
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# 固定字段顺序(diff 友好)
FIELD_ORDER = [
    "city", "province", "level", "city_code",
    "channel_type", "root_domain", "list_url",
    "source", "status", "last_probed_at", "probe_result", "notes",
]


class _OrderedDumper(yaml.SafeDumper):
    pass


def _dict_representer(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


_OrderedDumper.add_representer(dict, _dict_representer)


def load_catalog(path: Path) -> list[Channel]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    out = []
    for d in raw:
        d2 = dict(d)
        d2["status"] = ChannelStatus(d2["status"])
        out.append(Channel(**d2))
    return out


def save_catalog(catalog: list[Channel], path: Path) -> None:
    rows = []
    for ch in catalog:
        d = ch.to_dict()
        ordered = {k: d[k] for k in FIELD_ORDER if k in d}
        rows.append(ordered)
    path.write_text(
        yaml.dump(
            rows, Dumper=_OrderedDumper,
            allow_unicode=True, sort_keys=False, default_flow_style=False,
        ),
        encoding="utf-8",
    )
