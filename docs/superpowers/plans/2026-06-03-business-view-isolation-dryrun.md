# Business View Isolation Dry-run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible dry-run that identifies legacy or tainted `_meta/business_view/*.yaml` files, produces a machine-readable backup/isolation manifest, and renders a Chinese HTML review report without writing the vault.

**Architecture:** Add a focused audit module under `scripts/business_view_isolation/`. It reads business_view YAML files, classifies each file as `keep_current`, `isolate_legacy`, or `manual_review`, writes JSON/JSONL outputs under `state/business_view_isolation/<run>/`, and renders a self-contained HTML report. The tool is read-only for the vault; any future apply step must consume this dry-run output.

**Tech Stack:** Python 3, PyYAML, pytest, pathlib, argparse. No model calls.

---

## Files

- Create: `scripts/business_view_isolation/__init__.py`
- Create: `scripts/business_view_isolation/inventory.py`
- Create: `scripts/business_view_isolation/report.py`
- Create: `scripts/business_view_isolation/run.py`
- Create: `tests/business_view_isolation/test_inventory.py`
- Create: `tests/business_view_isolation/test_run.py`
- Create: `docs/superpowers/plans/2026-06-03-business-view-isolation-dryrun.md`

## Task 1: Inventory Classification

- [ ] Write failing tests in `tests/business_view_isolation/test_inventory.py`.

Test cases:

```python
def test_classifies_current_flow_as_keep(tmp_path):
    # extracted_by scripts/l2_themescore/run_2b.py + 3-key impact => keep_current

def test_classifies_legacy_claude_and_xiangcun_as_isolate(tmp_path):
    # extracted_by old oneshot + 乡村 key => isolate_legacy

def test_classifies_unparseable_yaml_as_manual_review(tmp_path):
    # broken yaml => manual_review, no crash
```

- [ ] Run: `python3 -m pytest tests/business_view_isolation/test_inventory.py -q`
  Expected: fail because module does not exist.

- [ ] Implement `inventory.py`.

Core API:

```python
EXPECTED_IMPACT_KEYS = {"加油", "充电", "电力_储能_V2G_交易"}
CURRENT_EXTRACTED_BY = "scripts/l2_themescore/run_2b.py"

@dataclass
class BusinessViewDecision:
    pid: str
    path: str
    action: str
    reasons: list[str]
    extracted_by: str | None
    extracted_model: str | None
    impact_keys: list[str]
    sha256: str

def inspect_business_view(path: Path, vault: Path) -> BusinessViewDecision: ...
def inventory_business_views(vault: Path) -> list[BusinessViewDecision]: ...
def summarize(decisions: list[BusinessViewDecision]) -> dict: ...
```

Rules:

- `manual_review`: YAML parse/read failure, missing `pid`, or path does not match expected file name.
- `keep_current`: `extracted_by == scripts/l2_themescore/run_2b.py` and impact keys are either empty or exactly the current three business keys.
- `isolate_legacy`: old `extracted_by`, old model, `unknown_legacy`, any `乡村`/`乡village` impact key, or impact key set not matching current three-key schema.

- [ ] Run the inventory test again and confirm pass.

## Task 2: Dry-run Outputs and HTML

- [ ] Write failing tests in `tests/business_view_isolation/test_run.py`.

Test cases:

```python
def test_dryrun_writes_manifest_summary_and_html(tmp_path):
    # outputs manifest.jsonl, summary.json, reports/business_view_isolation.html

def test_dryrun_does_not_modify_vault_files(tmp_path):
    # compare file content before/after dry-run
```

- [ ] Run: `python3 -m pytest tests/business_view_isolation/test_run.py -q`
  Expected: fail because run/report modules do not exist.

- [ ] Implement `report.py`.

HTML requirements:

- title: `旧 business_view 消费隔离 dry-run`
- state the run is read-only and does not write vault
- include counts by action
- include top reasons
- include sample rows for `isolate_legacy` and `manual_review`
- describe the future apply contract: backup outside vault, then isolate from consumable path; do not consume queue or PID exceptions.

- [ ] Implement `run.py`.

CLI:

```bash
python3 -m scripts.business_view_isolation.run dry-run \
  --vault "/Users/shaoziyuan/Documents/Zayn Main/政策分析" \
  --state state/business_view_isolation/dryrun_20260603
```

Outputs:

- `manifest.jsonl`
- `summary.json`
- `reports/business_view_isolation.html`

- [ ] Run dry-run tests and confirm pass.

## Task 3: Live Dry-run and Verification

- [ ] Run targeted tests:

```bash
python3 -m pytest tests/business_view_isolation -q
```

- [ ] Run live read-only dry-run against the real vault:

```bash
python3 -m scripts.business_view_isolation.run dry-run \
  --vault "/Users/shaoziyuan/Documents/Zayn Main/政策分析" \
  --state state/business_view_isolation/dryrun_20260603
```

- [ ] Verify principle and formatting gates:

```bash
python3 -m scripts.audit.principle_guard scripts/l2_themescore
git diff --check
```

- [ ] Commit and push:

```bash
git add scripts/business_view_isolation tests/business_view_isolation docs/superpowers/plans/2026-06-03-business-view-isolation-dryrun.md state/business_view_isolation/dryrun_20260603
git commit -m "feat: add business view isolation dry-run"
git push origin main
```

## Self-review

- Spec coverage: covers old `business_view` inventory, read-only dry-run, HTML report, manifest for later apply, and no PID exceptions.
- Placeholder scan: no TBD/TODO placeholders.
- Scope: intentionally excludes moving/deleting vault files; that requires a separate apply step consuming the dry-run.
