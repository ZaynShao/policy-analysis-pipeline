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
  /usr/bin/python3 -m scripts.service.notify "[S2] 03:00 信号链失败,查 signals.log"
}

set +e
(
  set -euo pipefail
  /usr/bin/flock -w 7200 9 || {
    set -a
    . "$NOTIFY_ENV"
    set +a
    cd "$REPO_DIR"
    /usr/bin/python3 -m scripts.service.notify "[S2] producer 锁等待超时(7200s),信号链跳过"
    exit 2
  }

  set -a
  . "$NOTIFY_ENV"
  set +a

  cd "$REPO_DIR"
  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.commentary_signals.run dry-run \
    --vault /vault \
    --state /state/commentary_signals/nightly

  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.market_intel_signals.run dry-run \
    --vault /vault \
    --manifest /state/source_ready/market_intel_manifest.jsonl \
    --state /state/market_intel_signals/nightly

  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.derived_signals.run preview \
    --commentary-state /state/commentary_signals/nightly \
    --market-state /state/market_intel_signals/nightly \
    --state /state/derived_signals/nightly

  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.derived_signals.run apply \
    --preview-state /state/derived_signals/nightly \
    --vault /vault

  /usr/bin/python3 -m scripts.service.produce_and_push \
    --vault-dir /root/policy-vault \
    --whitelist "1_extracted/commentary_signals.jsonl,1_extracted/market_intel_signals.jsonl" \
    --message "l2(signals): nightly derived signals"
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
