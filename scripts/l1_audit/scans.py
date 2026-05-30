"""残留 P_1900_*(date 真空占位)扫描。"""
from __future__ import annotations
from scripts.l1_audit.models import PolicyRecord, Finding


def scan_p1900(records: list[PolicyRecord]) -> list[Finding]:
    return [Finding(check="p1900", pid=r.pid, detail={},
                    proposed_action="date 真空 → backlog 人工补 date 重算 id")
            for r in records if r.pid.startswith("P_1900_")]
