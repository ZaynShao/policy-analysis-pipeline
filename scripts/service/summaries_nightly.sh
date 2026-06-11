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
  /usr/bin/python3 -m scripts.service.notify "[S2] 04:00 摘要增量失败,查 summaries.log"
}

set +e
(
  set -euo pipefail
  /usr/bin/flock -w 7200 9 || {
    set -a
    . "$NOTIFY_ENV"
    set +a
    cd "$REPO_DIR"
    /usr/bin/python3 -m scripts.service.notify "[S2] producer 锁等待超时(7200s),摘要增量跳过"
    exit 2
  }

  set -a
  . "$NOTIFY_ENV"
  set +a

  cd "$REPO_DIR"
  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.service.summaries_increment run \
    --vault /vault \
    --state-dir /state \
    --model deepseek-v4-flash \
    --provider openai

  /usr/bin/python3 -m scripts.service.produce_and_push \
    --vault-dir /root/policy-vault \
    --whitelist "1_extracted/policy_summaries.jsonl" \
    --message "l2(summaries): nightly increment"
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
