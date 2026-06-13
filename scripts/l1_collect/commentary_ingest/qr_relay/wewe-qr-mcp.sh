#!/bin/bash
# openclaw MCP stdio server 启动器:微信读书 QR 按需重发工具。
# 由 openclaw 网关按需 spawn(stdio)。env 从 policy-pipeline 配置文件载入,
# 凭据值留在 /etc/policy-pipeline/*.env,不进 openclaw.json。
# 部署见 docs/runbooks/qr-resend-mcp.md。
set -a
. /etc/policy-pipeline/notify.env
. /etc/policy-pipeline/commentary.env
set +a
# QR PNG 落点与 09:30 哨兵 cron 一致(不写进源码 checkout)
export WEWE_QR_DIR="${WEWE_QR_DIR:-/root/policy-pipeline-state/wewe_qr}"
cd /root/policy-pipeline-src
exec /root/policy-sentinel-venv/bin/python -m scripts.l1_collect.commentary_ingest.qr_relay.mcp_server
