#!/usr/bin/env bash
set -euo pipefail

BR_IF="${BR_IF-br-egress}"
GW_IP="${GW_IP-172.18.0.1}"
LISTENER_PORT="${LISTENER_PORT-15001}"
MARK="${MARK-1}"
ROUTE_TABLE="${ROUTE_TABLE-100}"
ALLOW_IPV6="${ALLOW_IPV6-0}"
GW_IP6="${GW_IP6-}"
ALLOWED_INFRA_CIDRS_CSV="${ALLOWED_INFRA_CIDRS_CSV-127.0.0.0/8,172.18.0.0/16}"
ALLOWED_INFRA_CIDRS6_CSV="${ALLOWED_INFRA_CIDRS6_CSV-}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

validate_inputs() {
  python3 - "$BR_IF" "$GW_IP" "$LISTENER_PORT" "$MARK" "$ROUTE_TABLE" "$ALLOW_IPV6" "$GW_IP6" "$ALLOWED_INFRA_CIDRS_CSV" "$ALLOWED_INFRA_CIDRS6_CSV" <<'PY'
import ipaddress
import sys

(
    _script,
    br_if,
    gw_ip,
    listener_port,
    mark,
    route_table,
    allow_ipv6,
    gw_ip6,
    infra4_csv,
    infra6_csv,
) = sys.argv

if not br_if:
    raise SystemExit("BR_IF must not be empty")

for name, value in {
    "LISTENER_PORT": listener_port,
    "MARK": mark,
    "ROUTE_TABLE": route_table,
}.items():
    try:
        parsed = int(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be numeric") from exc
    if parsed <= 0:
        raise SystemExit(f"{name} must be greater than zero")

try:
    ipaddress.IPv4Address(gw_ip)
except ipaddress.AddressValueError as exc:
    raise SystemExit(f"GW_IP must be a valid IPv4 address: {gw_ip}") from exc

for cidr in [item.strip() for item in infra4_csv.split(",") if item.strip()]:
    try:
        ipaddress.IPv4Network(cidr, strict=False)
    except ValueError as exc:
        raise SystemExit(f"invalid IPv4 CIDR in ALLOWED_INFRA_CIDRS_CSV: {cidr}") from exc

if allow_ipv6 not in {"0", "1", "false", "true", "False", "True"}:
    raise SystemExit("ALLOW_IPV6 must be one of 0, 1, true, false")

ipv6_enabled = allow_ipv6.lower() in {"1", "true"}
if ipv6_enabled:
    if not gw_ip6:
        raise SystemExit("GW_IP6 is required when ALLOW_IPV6=1")
    try:
        ipaddress.IPv6Address(gw_ip6)
    except ipaddress.AddressValueError as exc:
        raise SystemExit(f"GW_IP6 must be a valid IPv6 address: {gw_ip6}") from exc
    for cidr in [item.strip() for item in infra6_csv.split(",") if item.strip()]:
        try:
            ipaddress.IPv6Network(cidr, strict=False)
        except ValueError as exc:
            raise SystemExit(f"invalid IPv6 CIDR in ALLOWED_INFRA_CIDRS6_CSV: {cidr}") from exc
PY
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

require_cmd nft
require_cmd ip
require_cmd python3
validate_inputs

declare -a ALLOWED_INFRA_CIDRS=()
declare -a ALLOWED_INFRA_CIDRS6=()
read_csv_into_array "$ALLOWED_INFRA_CIDRS_CSV" ALLOWED_INFRA_CIDRS
read_csv_into_array "$ALLOWED_INFRA_CIDRS6_CSV" ALLOWED_INFRA_CIDRS6

if ! nft list table inet egressd >/dev/null 2>&1; then
  nft add table inet egressd
fi

if ! nft list chain inet egressd prerouting >/dev/null 2>&1; then
  nft 'add chain inet egressd prerouting { type filter hook prerouting priority -150; policy accept; }'
fi

nft flush chain inet egressd prerouting || true

nft add rule inet egressd prerouting iifname "$BR_IF" ip daddr $GW_IP tcp dport $LISTENER_PORT accept
nft add rule inet egressd prerouting iifname "$BR_IF" ip daddr $GW_IP udp dport 53 accept
nft add rule inet egressd prerouting iifname "$BR_IF" ip daddr $GW_IP tcp dport 53 accept

nft add rule inet egressd prerouting iifname "$BR_IF" udp sport 68 udp dport 67 accept
nft add rule inet egressd prerouting iifname "$BR_IF" udp sport 67 udp dport 68 accept

for cidr in "${ALLOWED_INFRA_CIDRS[@]}"; do
  nft add rule inet egressd prerouting iifname "$BR_IF" ip daddr $cidr accept || true
done

nft add rule inet egressd prerouting iifname "$BR_IF" udp dport 53 ip daddr != $GW_IP drop
nft add rule inet egressd prerouting iifname "$BR_IF" tcp dport 53 ip daddr != $GW_IP drop
nft add rule inet egressd prerouting iifname "$BR_IF" tcp dport $LISTENER_PORT accept

if [[ "${ALLOW_IPV6,,}" == "1" || "${ALLOW_IPV6,,}" == "true" ]]; then
  nft add rule inet egressd prerouting iifname "$BR_IF" ip6 daddr $GW_IP6 tcp dport $LISTENER_PORT accept
  nft add rule inet egressd prerouting iifname "$BR_IF" ip6 daddr $GW_IP6 udp dport 53 accept
  nft add rule inet egressd prerouting iifname "$BR_IF" ip6 daddr $GW_IP6 tcp dport 53 accept
  for cidr in "${ALLOWED_INFRA_CIDRS6[@]}"; do
    nft add rule inet egressd prerouting iifname "$BR_IF" ip6 daddr $cidr accept || true
  done
  nft add rule inet egressd prerouting iifname "$BR_IF" udp dport 53 ip6 daddr != $GW_IP6 drop
  nft add rule inet egressd prerouting iifname "$BR_IF" tcp dport 53 ip6 daddr != $GW_IP6 drop
  nft add rule inet egressd prerouting iifname "$BR_IF" ip6 nexthdr tcp meta mark set $MARK tproxy to :$LISTENER_PORT
else
  nft add rule inet egressd prerouting iifname "$BR_IF" meta nfproto ipv6 drop
fi

nft add rule inet egressd prerouting iifname "$BR_IF" meta l4proto tcp meta mark set $MARK tproxy to :$LISTENER_PORT

ip rule del fwmark $MARK table $ROUTE_TABLE 2>/dev/null || true
ip rule add fwmark $MARK table $ROUTE_TABLE
ip route del local 0/0 dev lo table $ROUTE_TABLE 2>/dev/null || true
ip route add local 0.0.0.0/0 dev lo table $ROUTE_TABLE

if [[ "${ALLOW_IPV6,,}" == "1" || "${ALLOW_IPV6,,}" == "true" ]]; then
  ip -6 rule del fwmark $MARK table $ROUTE_TABLE 2>/dev/null || true
  ip -6 rule add fwmark $MARK table $ROUTE_TABLE
  ip -6 route del local ::/0 dev lo table $ROUTE_TABLE 2>/dev/null || true
  ip -6 route add local ::/0 dev lo table $ROUTE_TABLE
fi

echo "configured nftables tproxy interception for $BR_IF -> $GW_IP:$LISTENER_PORT (ipv6=${ALLOW_IPV6})"
