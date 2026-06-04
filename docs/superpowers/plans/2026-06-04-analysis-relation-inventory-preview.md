# Analysis Relation Inventory Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ③-A relation asset audit preview that inventories stale vault relations against the current tracked raw policy corpus.

**Architecture:** Add `scripts/analysis_relation_inventory` with a read-only preview CLI. It reads tracked `0_raw/policies/*.md` via git, reads old `1_extracted/relations/*.jsonl`, labels each relation with locator and risk flags, writes machine JSON/JSONL plus a Chinese HTML report under `state/analysis_layer/preview_YYYYMMDD/`.

**Tech Stack:** Python standard library, pytest, existing CLI pattern using `python3 -m scripts.<tool>.run`.

---

## Files

- Create: `scripts/analysis_relation_inventory/__init__.py`
- Create: `scripts/analysis_relation_inventory/run.py`
- Create: `scripts/analysis_relation_inventory/report.py`
- Create: `tests/analysis_relation_inventory/__init__.py`
- Create: `tests/analysis_relation_inventory/test_run.py`
- Create live preview under: `state/analysis_layer/preview_20260604/`
- Modify: `docs/BACKLOG.md`

## Task 1: Add Failing Tests

**Files:**
- Create: `tests/analysis_relation_inventory/__init__.py`
- Create: `tests/analysis_relation_inventory/test_run.py`

- [ ] **Step 1: Test tracked-policy indexing ignores untracked raw**

Create a temp vault git repo with one tracked policy and one untracked policy. Assert the preview raw index counts only the tracked policy and reports the untracked policy count separately.

- [ ] **Step 2: Test relation locator flags**

Create relation rows covering:

- both endpoints located
- `to` missing
- `P_1900` endpoint
- archive relation file
- low-confidence relation type

Assert output rows include `from_status`, `to_status`, and `flags`.

- [ ] **Step 3: Test preview outputs**

Assert preview writes:

- `relation_inventory.json`
- `relation_rows.jsonl`
- `reports/relation_inventory_preview.html`

- [ ] **Step 4: Run red tests**

Run:

```bash
python3 -m pytest -q tests/analysis_relation_inventory
```

Expected: fail because `scripts.analysis_relation_inventory` does not exist yet.

## Task 2: Implement Preview CLI

**Files:**
- Create: `scripts/analysis_relation_inventory/__init__.py`
- Create: `scripts/analysis_relation_inventory/run.py`
- Create: `scripts/analysis_relation_inventory/report.py`

- [ ] **Step 1: Implement tracked policy listing**

Use `git -C <vault> ls-files '0_raw/policies/*.md'` so untracked raw files are not silently added to the audit baseline.

- [ ] **Step 2: Implement frontmatter id/alias extraction**

Parse only frontmatter between first two `---` fences. Extract:

- `id`
- `aliases`
- `title`

- [ ] **Step 3: Implement relation loading**

Read `1_extracted/relations/*.jsonl` except `_index_by_policy/` markdown. Include archive jsonl files but flag them with `archive_relation_file`.

- [ ] **Step 4: Implement row classification**

For each relation row:

- locate `from` and `to` against current id/aliases
- flag `from_missing`, `to_missing`, `from_p1900`, `to_p1900`
- flag relation families:
  - `high_precision_candidate`: `references`, `cites_basis`, `supersedes`, `clarifies`
  - `semantic_low_confidence`: `derives_from`, `aligns_with`, `extends`
  - `mixed_precision`: `iterates`
  - `unknown_relation_type`
- keep old row as `source_row` for audit, not as accepted output

- [ ] **Step 5: Implement summary and HTML report**

Summary must include:

- tracked policy count
- untracked policy count
- relation file counts
- row counts by relation
- row counts by flag
- endpoint missing counts
- archive row counts
- recommendation: audit only, no apply

- [ ] **Step 6: Run green tests**

Run:

```bash
python3 -m pytest -q tests/analysis_relation_inventory
```

Expected: pass.

## Task 3: Run Live Preview

**Files:**
- Create: `state/analysis_layer/preview_20260604/relation_inventory.json`
- Create: `state/analysis_layer/preview_20260604/relation_rows.jsonl`
- Create: `state/analysis_layer/preview_20260604/reports/relation_inventory_preview.html`

- [ ] **Step 1: Run preview**

Run:

```bash
python3 -m scripts.analysis_relation_inventory.run preview \
  --vault "/Users/shaoziyuan/Documents/Zayn Main/政策分析" \
  --state state/analysis_layer/preview_20260604
```

Expected: state files and HTML report are created. The report must mention the current untracked raw file count and that untracked raw is excluded from the audit baseline.

- [ ] **Step 2: Update backlog**

Modify `docs/BACKLOG.md` B10 to record that relation inventory preview has been produced and is audit-only.

## Task 4: Verify and Commit

**Files:**
- Commit all created and modified engineering files.

- [ ] **Step 1: Verify**

Run:

```bash
python3 -m pytest -q tests/analysis_relation_inventory
python3 -m pytest -q
python3 -m scripts.audit.principle_guard scripts/l2_themescore
git diff --check
git -C "/Users/shaoziyuan/Documents/Zayn Main/政策分析" status --short --branch
```

Expected:

- tests pass
- principle guard passes
- vault remains unchanged except the known pre-existing untracked raw file

- [ ] **Step 2: Commit and push**

Run:

```bash
git add docs/superpowers/plans/2026-06-04-analysis-relation-inventory-preview.md \
  docs/BACKLOG.md scripts/analysis_relation_inventory tests/analysis_relation_inventory
git add -f state/analysis_layer/preview_20260604
git commit -m "feat: add relation inventory preview"
git push
```

Expected: engineering repo is clean and pushed.
