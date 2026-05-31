from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChannelEntry:
    domain: str
    issuer_short: str                 # id 前缀(地方=省级码)
    issuer_canonical: str             # 渠道级机关名(粗)
    region: dict                      # {level, code, name}


@dataclass
class ResolvedField:
    value: object
    method: str                       # §C method 枚举
    confidence: float
    from_val: str = ""                # 原值(审计用)


@dataclass
class Conflict:
    field: str
    reason: str
    signals: dict = field(default_factory=dict)


@dataclass
class ResolvedIdentity:
    pid: str
    fields: dict = field(default_factory=dict)        # name -> ResolvedField(待写)
    conflicts: list = field(default_factory=list)     # list[Conflict](入队列)

    def set_field(self, name, value, method, confidence, from_val=""):
        self.fields[name] = ResolvedField(value, method, confidence, from_val)

    def add_conflict(self, field_name, reason, signals=None):
        self.conflicts.append(Conflict(field_name, reason, signals or {}))

    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0


@dataclass
class QueueRecord:
    pid: str
    field: str
    reason: str
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"pid": self.pid, "field": self.field,
                "reason": self.reason, "signals": self.signals}
