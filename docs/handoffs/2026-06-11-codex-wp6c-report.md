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

## 续跑 2

Date: 2026-06-11
Executor: Codex
Target: `root@8.216.59.173`, repo `/root/policy-pipeline-src`

### Result

Stopped before cron installation.

Reason: after installing the host Python dependency, the required manual run of `scripts.l1_review_consumer.sync_l1_pool` failed because the server host could not resolve the Postgres hostname `heng-pg`.

### 1. Install host Python dependency

Command shape:

```bash
apt-get update
apt-get install -y python3-psycopg2
/usr/bin/python3 -c "import psycopg2; print(psycopg2.__version__)"
```

Observed package changes:

```text
The following NEW packages will be installed:
  libpq5 python3-psycopg2
```

Observed import check:

```text
2.9.11 (dt dec pq3 ext lo64)
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
  File "/root/policy-pipeline-src/scripts/l1_review_consumer/sync_l1_pool.py", line 53, in main
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
  File "/usr/lib/python3/dist-packages/psycopg2/__init__.py", line 122, in connect
    conn = _connect(dsn, connection_factory=connection_factory, **kwasync)
psycopg2.OperationalError: could not translate host name "heng-pg" to address: Temporary failure in name resolution

EXIT=1
```

Exit code: `1`

### Not run

- `scripts.l1_review_consumer.poll_l1_verdicts` was not run because step 2 failed and the handoff says to stop on any exception.
- The two `l1_review_consumer` cron lines were not installed.
- `crontab -l | grep -c l1_review_consumer` was not run as a post-install verification because installation did not happen.
- The expected post-install total count was not reached because the package stopped before cron mutation.

Post-stop crontab verification:

```text
crontab -l | grep -c l1_review_consumer
0
crontab -l | wc -l
30
```

### Gate status

- Credential values remained blind.
- Vault was not touched.
- No cron mutation occurred.
- No PG queue mutation completed; the process failed while opening the database connection.

### Recommended next step

Fix the host-side Postgres connection address for `/usr/bin/python3` runs before installing these host cron lines. The current `DATABASE_URL` hostname `heng-pg` is not resolvable from the server host namespace, so either the cron path needs a host-resolvable DSN or the consumer needs to run in a namespace where `heng-pg` resolves.

## 续跑 3

Date: 2026-06-11
Executor: Codex
Target: `root@8.216.59.173`, repo `/root/policy-pipeline-src`

### Result

Cron installed in container form.

Important caveat: `sync_l1_pool` connected to PG and exited `0`, but it was not a pure empty-pool no-op. It saw 15 `fetch_fail` rows and skipped all 15 because PG `L1ReviewQueue.id` is `NOT NULL` while the current insert shape sends `id = null`. No connection failure occurred.

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
 + b131883...397b719 main       -> origin/main  (forced update)
HEAD is now at 397b719 docs(runbook): review_consumer cron runs in policy-producer container (heng-pg only resolvable on platform-net)
397b719
```

Exit code: `0`

### 2. Manual run: `sync_l1_pool`

Command shape:

```bash
cd /root/policy-pipeline-src
docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.l1_review_consumer.sync_l1_pool
```

No env values were printed.

Observed output:

```text
Container policy-pipeline-src-policy-producer-run-c5fca638bcf0 Creating
Container policy-pipeline-src-policy-producer-run-c5fca638bcf0 Created
skip fetch_fail::http://scjg.tj.gov.cn/: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
DETAIL:  Failing row contains (null, fetch_fail::http://scjg.tj.gov.cn/, fetch_fail, http://scjg.tj.gov.cn/, fetch_error_after_retry, retry, null, , 天津市__政府网__www.tj.gov.cn, 天津市__政府网__www.tj.gov.cn, null, null, null, null, null, null, null, f, 2026-06-11 10:01:47.545).

skip fetch_fail::https://zz.hnzwfw.gov.cn/zzzw/item/frindex.do?type=2&areaCode=410100000000&themeName=%E6%8A%95%E8%B5%84%E5%AE%A1%E6%89%B9&dictValue=08: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::https://www.changzhou.gov.cn/vote/survey.php?a=vinfo&bid=1861: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::https://www.ndrc.gov.cn/xwdt/202606/t20260601_1405631.html: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::https://www.ndrc.gov.cn/xwdt/202605/t20260520_1405314.html: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::https://www.ndrc.gov.cn/xwdt/202604/t20260424_1404879.html: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::https://gxt.hebei.gov.cn/hbgyhxxht/ztzl11/gxrsgxs/2026042909442068878/index.html: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::https://gxt.hebei.gov.cn/hbgyhxxht/ztzl11/gxrsgxs/2025102416012298445/index.html: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::http://nyj.yn.gov.cn: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::http://scjdglj.gxzf.gov.cn/zwgk/t27742710.shtml: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::http://scjdglj.gxzf.gov.cn/zwgk/t27686560.shtml: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::http://scjdglj.gxzf.gov.cn/zwgk/t27544920.shtml: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::http://scjdglj.gxzf.gov.cn/zwgk/t27542899.shtml: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::https://amr.hainan.gov.cn/zw/202606/t20260603_4086675.html: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
skip fetch_fail::https://m.12371.gov.cn/app/template/displayTemplate/news/newsDetail/40/508665.html?isShare=true: null value in column "id" of relation "L1ReviewQueue" violates not-null constraint
forward synced 0/15 rows -> PG L1ReviewQueue
EXIT=0
```

Exit code: `0`

### 3. Manual run: `poll_l1_verdicts`

Command shape:

```bash
cd /root/policy-pipeline-src
docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.l1_review_consumer.poll_l1_verdicts
```

No env values were printed.

Observed output:

```text
Container policy-pipeline-src-policy-producer-run-da235c8052d4 Creating
Container policy-pipeline-src-policy-producer-run-da235c8052d4 Created
reverse polled 0 verdicts -> /app/state/l1_review/verdicts.jsonl (重核 + review GC 在 applier,见 handoff)
EXIT=0
```

Exit code: `0`

### 4. Cron install and verification

Installed runbook container-form lines:

```cron
5 10 * * * cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.l1_review_consumer.sync_l1_pool >> /var/log/policy-pipeline/review_consumer.log 2>&1
*/30 8-22 * * * cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.l1_review_consumer.poll_l1_verdicts >> /var/log/policy-pipeline/review_consumer.log 2>&1
```

Verification:

```text
crontab -l | grep -c l1_review_consumer
2
crontab -l | wc -l
32
```

### Gate status

- Credential values remained blind.
- Vault was not touched.
- Both consumer modules ran inside `policy-producer`, where `heng-pg` resolves through the container network.
- Cron mutation was limited to removing any existing `l1_review_consumer` lines and appending the two runbook container-form lines.
- PG forward sync did not insert rows because all 15 current pool rows hit the `L1ReviewQueue.id` non-null constraint and were skipped by the script.

### Recommended next step

Fix the B14 PG insert contract mismatch: either `sync_l1_pool` must provide a deterministic `id`, or the `L1ReviewQueue.id` column must have the default expected by the service schema. Until then, the cron is installed but forward sync will keep skipping current pool rows.
