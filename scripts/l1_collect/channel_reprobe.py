"""Candidate channel reprobe lifecycle.

Automatic promotion is deliberately narrow: a candidate is promoted only when
``discover_one`` returns ``ChannelStatus.验证``, which means the list-page probe
passed and institution matching passed. Ambiguous probe-ok candidates stay in
the review pool for human/B14 handling. Downstream scanning still filters titles
with KEYWORDS and each article still passes policy_gate, so a bad channel should
reduce hits rather than write dirty policy data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import review_pool
from .channel_catalog import Channel, ChannelStatus, load_catalog, save_catalog
from .channel_discovery import discover_one

CAT = Path("state/T1_channels/channel_catalog.yaml")


def _stamp(ch: Channel, note: str) -> None:
    """Append a provenance note once."""
    if note not in (ch.notes or ""):
        ch.notes = f"{ch.notes}; {note}" if ch.notes else note


def reprobe_candidate(ch: Channel, *, today: str) -> tuple[Channel, str]:
    """Re-run discovery for one candidate channel.

    Returns ``(channel, outcome)`` where outcome is one of
    ``promoted``, ``ambiguous``, or ``still_candidate``.
    """
    target = {
        "city": ch.city,
        "province": ch.province,
        "level": ch.level,
        "city_code": ch.city_code,
        "channel_type": ch.channel_type,
        "root_domain": ch.root_domain or None,
    }
    fresh = discover_one(target)
    if fresh is None:
        return ch, "still_candidate"

    ch.last_probed_at = fresh.last_probed_at
    ch.probe_result = fresh.probe_result
    if fresh.list_url:
        ch.list_url = fresh.list_url
    if fresh.root_domain:
        ch.root_domain = fresh.root_domain

    if fresh.status == ChannelStatus.验证:
        ch.status = ChannelStatus.验证
        _stamp(ch, f"auto-promoted-{today}-probe-ok")
        return ch, "promoted"
    if fresh.probe_result == "ok":
        review_pool.append(review_pool.candidate_entry(ch))
        return ch, "ambiguous"
    return ch, "still_candidate"


def reprobe_candidates(
    catalog: list[Channel],
    *,
    only_types=None,
    limit=None,
    dry_run=True,
    today=None,
) -> dict:
    """Reprobe candidate channels and optionally persist catalog changes."""
    cands = [c for c in catalog if c.status == ChannelStatus.候选]
    if only_types:
        cands = [c for c in cands if c.channel_type in only_types]
    if limit is not None:
        cands = cands[:limit]

    promoted = ambiguous = 0
    for c in cands:
        _, outcome = reprobe_candidate(c, today=today)
        promoted += outcome == "promoted"
        ambiguous += outcome == "ambiguous"

    if not dry_run:
        save_catalog(catalog, CAT)
    return {"scanned": len(cands), "promoted": promoted, "ambiguous": ambiguous}


def _cst_today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _parse_only_types(raw: str | None):
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprobe L1 candidate channels.")
    parser.add_argument("--only-types", help="Comma-separated channel types, e.g. 能源局,发改委,能源监管")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--apply", action="store_true", help="Persist catalog changes. Default is dry-run.")
    parser.add_argument("--today", default=None, help="CST date string for provenance notes, e.g. 2026-06-15")
    args = parser.parse_args()

    catalog = load_catalog(CAT)
    stats = reprobe_candidates(
        catalog,
        only_types=_parse_only_types(args.only_types),
        limit=args.limit,
        dry_run=not args.apply,
        today=args.today or _cst_today(),
    )
    mode = "apply" if args.apply else "dry-run"
    print(f"mode={mode} scanned={stats['scanned']} promoted={stats['promoted']} ambiguous={stats['ambiguous']}")


if __name__ == "__main__":
    main()
