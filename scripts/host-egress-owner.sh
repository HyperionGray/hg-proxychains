#!/usr/bin/env bash
set -euo pipefail

EGRESS_UID="${EGRESS_UID-997}"
UPSTREAM_IPS_CSV="${UPSTREAM_IPS_CSV-203.0.113.10,203.0.113.11,1.1.1.1}"
UPSTREAM_IPS6_CSV="${UPSTREAM_IPS6_CSV-}"
UPSTREAM_PORTS="${UPSTREAM_PORTS-3128,443}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

read_csv_into_array() {
  local raw="$1"
  local -n out_ref="$2"
  IFS=',' read -r -a out_ref <<< "$raw"
  local cleaned=()
  local item
  for item in "${out_ref[@]}"; do
    item="${item#"${item%%[![:space:]]*}"}"
    item="${item%"${item##*[![:space:]]}"}"
    if [[ -n "$item" ]]; then
      cleaned+=("$item")
    fi
  done
  out_ref=("${cleaned[@]}")
}

validate_inputs() {
  python3 - "$EGRESS_UID" "$UPSTREAM_IPS_CSV" "$UPSTREAM_IPS6_CSV" "$UPSTREAM_PORTS" <<'PY'
import ipaddress
import sys

_script, uid_text, ips4_csv, ips6_csv, ports_csv = sys.argv

try:
    uid = int(uid_text)
except ValueError as exc:
    raise SystemExit("EGRESS_UID must be numeric") from exc

if uid <= 0:
    raise SystemExit("EGRESS_UID must be greater than zero")

ipv4_values = [item.strip() for item in ips4_csv.split(",") if item.strip()]
ipv6_values = [item.strip() for item in ips6_csv.split(",") if item.strip()]
port_values = [item.strip() for item in ports_csv.split(",") if item.strip()]

if not ipv4_values and not ipv6_values:
    raise SystemExit("at least one upstream IP must be configured")
if not port_values:
    raise SystemExit("UPSTREAM_PORTS must not be empty")

for value in ipv4_values:
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise SystemExit(f"invalid IPv4 upstream address: {value}") from exc

for value in ipv6_values:
    try:
        ipaddress.IPv6Address(value)
    except ipaddress.AddressValueError as exc:
        raise SystemExit(f"invalid IPv6 upstream address: {value}") from exc

for value in port_values:
    try:
        port = int(value)
    except ValueError as exc:
        raise SystemExit(f"invalid upstream port: {value}") from exc
    if not 1 <= port <= 65535:
        raise SystemExit(f"invalid upstream port: {value}")
PY
}

require_cmd nft
require_cmd python3
validate_inputs

declare -a IPS=()
declare -a IPS6=()
declare -a PORTS=()
read_csv_into_array "$UPSTREAM_IPS_CSV" IPS
read_csv_into_array "$UPSTREAM_IPS6_CSV" IPS6
read_csv_into_array "$UPSTREAM_PORTS" PORTS

IP_SET=$(printf "%s, " "${IPS[@]}")
IP_SET="${IP_SET%, }"
IP6_SET=$(printf "%s, " "${IPS6[@]}")
IP6_SET="${IP6_SET%, }"
PORT_SET=$(printf "%s, " "${PORTS[@]}")
PORT_SET="${PORT_SET%, }"

if ! nft list table inet egressd_host >/dev/null 2>&1; then
  nft add table inet egressd_host
fi

if ! nft list chain inet egressd_host output >/dev/null 2>&1; then
  nft 'add chain inet egressd_host output { type filter hook output priority 0; policy accept; }'
fi

nft flush chain inet egressd_host output || true

if [[ -n "$IP_SET" ]]; then
  nft add rule inet egressd_host output meta skuid $EGRESS_UID ip daddr { $IP_SET } tcp dport { $PORT_SET } accept
  nft add rule inet egressd_host output ip daddr { $IP_SET } tcp dport { $PORT_SET } drop
fi

if [[ -n "$IP6_SET" ]]; then
  nft add rule inet egressd_host output meta skuid $EGRESS_UID ip6 daddr { $IP6_SET } tcp dport { $PORT_SET } accept
  nft add rule inet egressd_host output ip6 daddr { $IP6_SET } tcp dport { $PORT_SET } drop
fi

echo "restricted upstream egress to skuid=$EGRESS_UID for IPs={$IP_SET} IPv6={$IP6_SET:-none} ports={$PORT_SET}"
