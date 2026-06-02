"""Principle guard for policy-analysis pipeline source code."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


POLICY_ID_RE = re.compile(r"\bP_(?:19|20)\d{2}_[A-Z0-9]+_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)?\b")


def _iter_files(paths):
    for path in paths:
        path = Path(path)
        if path.is_dir():
            yield from sorted(path.rglob("*.py"))
        elif path.exists():
            yield path


def find_policy_id_literals(paths) -> list[dict]:
    """Return policy-id literals found in source files.

    2-B code should express decisions as global rules, registries, or gates, not
    as per-policy branches. Human review reports can name PIDs; source code in
    the pipeline should not.
    """
    findings = []
    for path in _iter_files(paths):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in POLICY_ID_RE.finditer(line):
                findings.append({
                    "path": str(path),
                    "line": lineno,
                    "policy_id": match.group(0),
                })
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["scripts/l2_themescore"])
    args = parser.parse_args(argv)

    findings = find_policy_id_literals(args.paths)
    for item in findings:
        print(f"{item['path']}:{item['line']}: hardcoded policy id {item['policy_id']}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
