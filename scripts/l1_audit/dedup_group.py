"""存量重复分组:三维(URL/文号/标题)任一命中即同组(复用 dedup 归一化)。
每组留 date 最早者,其余提议迁 _duplicates。"""
from __future__ import annotations
from scripts.l1_collect.dedup import normalize_url, normalize_official_number, normalize_title
from scripts.l1_audit.models import PolicyRecord, Finding


class _UF:  # union-find
    def __init__(self): self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        self.p[self.find(b)] = self.find(a)


def group_duplicates(records: list[PolicyRecord]) -> list[Finding]:
    uf = _UF()
    for dim, norm, attr in (
        ("url", normalize_url, "url"),
        ("off", normalize_official_number, "official_number"),
        ("title", normalize_title, "title"),
    ):
        seen = {}
        for r in records:
            key = norm(getattr(r, attr))
            if not key:
                continue
            if key in seen:
                uf.union(seen[key].pid, r.pid)
            else:
                seen[key] = r
    by_pid = {r.pid: r for r in records}
    groups: dict[str, list[str]] = {}
    for r in records:
        groups.setdefault(uf.find(r.pid), []).append(r.pid)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda p: (by_pid[p].date or "9999", p))  # 最早在前
        keep, dups = members[0], members[1:]
        out.append(Finding(check="dedup", pid=keep,
                           detail={"keep": keep, "dups": dups},
                           proposed_action=f"留 {keep};{dups} 迁 _duplicates/"))
    return out
