#!/usr/bin/env bash
set -euo pipefail

REPO_DIR=/root/policy-pipeline-src
LOCK_FILE=/var/lock/policy-pipeline-producer.lock
NOTIFY_ENV=/etc/policy-pipeline/notify.env

notify_failure() {
  set -a
  . "$NOTIFY_ENV"
  set +a
  cd "$REPO_DIR"
  /usr/bin/python3 -m scripts.service.notify "[S2] 03:30 上下文链失败,查 contexts.log"
}

set +e
(
  set -euo pipefail
  /usr/bin/flock -w 7200 9 || {
    set -a
    . "$NOTIFY_ENV"
    set +a
    cd "$REPO_DIR"
    /usr/bin/python3 -m scripts.service.notify "[S2] producer 锁等待超时(7200s),上下文链跳过"
    exit 2
  }

  set -a
  . "$NOTIFY_ENV"
  set +a

  cd "$REPO_DIR"
  docker compose -f docker-compose.server.yml run --rm policy-producer \
    sh -lc 'rm -rf /state/signal_context/nightly /state/analysis_layer/nightly /state/analysis_layer/nightly_inventory'

  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.signal_context.run preview \
    --vault /vault \
    --state /state/signal_context/nightly \
    --blocked-signals /state/derived_signals/nightly/blocked_signals.jsonl

  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.analysis_context.run preview \
    --relations /vault/1_extracted/relations/relations_canonical.jsonl \
    --policy-context /state/signal_context/nightly/policy_context.jsonl \
    --state /state/analysis_layer/nightly

  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.analysis_relation_inventory.run preview \
    --vault /vault \
    --state /state/analysis_layer/nightly_inventory
) 9>"$LOCK_FILE"
status=$?
set -e

if [ "$status" -eq 0 ]; then
  exit 0
fi
if [ "$status" -eq 2 ]; then
  exit 1
fi

notify_failure
exit "$status"
