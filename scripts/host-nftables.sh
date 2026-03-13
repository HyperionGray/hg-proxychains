#!/usr/bin/env bash
set -euo pipefail

BR_IF="${BR_IF:-br-egress}"
GW_IP="${GW_IP:-172.18.0.1}"
LISTENER_PORT="${LISTENER_PORT:-15001}"
MARK="${MARK:-1}"
ALLOWED_INFRA_CIDRS=("127.0.0.0/8" "172.18.0.0/16")

if ! nft list table inet egressd >/dev/null 2>&1; then
  nft add table inet egressd
fi

if ! nft list chain inet egressd prerouting >/dev/null 2>&1; then
  nft 'add chain inet egressd prerouting { type filter hook prerouting priority 0; }'
fi

if ! nft list chain inet egressd tproxy >/dev/null 2>&1; then
  nft 'add chain inet egressd tproxy { type nat hook prerouting priority -100; }'
fi

nft flush chain inet egressd prerouting || true
nft flush chain inet egressd tproxy || true

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

nft add rule inet egressd prerouting iifname "$BR_IF" tcp dport != $LISTENER_PORT meta mark set $MARK
nft add rule inet egressd tproxy meta mark $MARK tproxy to :$LISTENER_PORT

ip rule del fwmark $MARK table 100 2>/dev/null || true
ip rule add fwmark $MARK table 100
ip route del local 0/0 dev lo table 100 2>/dev/null || true
ip route add local 0.0.0.0/0 dev lo table 100

echo "configured nftables tproxy interception for $BR_IF -> $GW_IP:$LISTENER_PORT"
