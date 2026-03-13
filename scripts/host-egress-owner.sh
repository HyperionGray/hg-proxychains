#!/usr/bin/env bash
set -euo pipefail

EGRESS_UID="${EGRESS_UID:-997}"
UPSTREAM_IPS_CSV="${UPSTREAM_IPS_CSV:-203.0.113.10,203.0.113.11,1.1.1.1}"
UPSTREAM_PORTS="${UPSTREAM_PORTS:-3128,443}"

IFS=',' read -r -a IPS <<< "$UPSTREAM_IPS_CSV"
IFS=',' read -r -a PORTS <<< "$UPSTREAM_PORTS"

IP_SET=$(printf "%s, " "${IPS[@]}")
IP_SET="${IP_SET%, }"
PORT_SET=$(printf "%s, " "${PORTS[@]}")
PORT_SET="${PORT_SET%, }"

if ! nft list table inet egressd_host >/dev/null 2>&1; then
  nft add table inet egressd_host
fi

if ! nft list chain inet egressd_host output >/dev/null 2>&1; then
  nft 'add chain inet egressd_host output { type filter hook output priority 0; policy accept; }'
fi

nft flush chain inet egressd_host output || true

nft add rule inet egressd_host output meta skuid $EGRESS_UID ip daddr { $IP_SET } tcp dport { $PORT_SET } accept
nft add rule inet egressd_host output ip daddr { $IP_SET } tcp dport { $PORT_SET } drop

echo "restricted upstream egress to skuid=$EGRESS_UID for IPs={$IP_SET} ports={$PORT_SET}"
