# WP-6c-resume review_consumer server wiring report

Date: 2026-06-11
Executor: Codex
Target: `root@8.216.59.173`, repo `/root/policy-pipeline-src`

## Result

Stopped before cron installation.

Reason: the required manual run of `scripts.l1_review_consumer.sync_l1_pool` failed on the server host Python because `psycopg2` is not installed.

## Steps run

### 1. Sync server repo to main

Command shape:

```bash
cd /root/policy-pipeline-src
git fetch --depth=1 origin main
git reset --hard origin/main
git rev-parse --short HEAD
```

Observed output:

```text
From github-pipeline:ZaynShao/policy-analysis-pipeline
 * branch            main       -> FETCH_HEAD
 + 1d0b91d...b131883 main       -> origin/main  (forced update)
HEAD is now at b131883 docs: wire l1 review consumer cron
b131883
```

Exit code: `0`

### 2. Manual run: `sync_l1_pool`

Command shape:

```bash
cd /root/policy-pipeline-src
set -a
. /etc/policy-pipeline/pipeline.env
. /etc/policy-pipeline/notify.env
set +a
/usr/bin/python3 -m scripts.l1_review_consumer.sync_l1_pool
```

No env values were printed.

Observed output:

```text
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/root/policy-pipeline-src/scripts/l1_review_consumer/sync_l1_pool.py", line 74, in <module>
    main()
    ~~~~^^
  File "/root/policy-pipeline-src/scripts/l1_review_consumer/sync_l1_pool.py", line 51, in main
    import psycopg2
ModuleNotFoundError: No module named 'psycopg2'

EXIT=1
```

Exit code: `1`

## Not run

- `scripts.l1_review_consumer.poll_l1_verdicts` was not run because step 2 failed and the handoff says to stop on any exception.
- The two `l1_review_consumer` cron lines were not installed.
- `crontab -l | grep -c l1_review_consumer` was not run after installation because installation did not happen.
- Current crontab total line count was not recorded because the package stopped before cron mutation.

## Gate status

- Credential values remained blind.
- Vault was not touched.
- No PG queue mutation beyond the failed import attempt occurred.
- No cron mutation occurred.

## Recommended next step

Install the server-side Python dependency used by the host `review_consumer` modules, then rerun this handoff from step 2. The likely minimal fix is to provide `psycopg2` or `psycopg2-binary` to `/usr/bin/python3` on the server, using the same dependency policy as the rest of the server host Python utilities.
