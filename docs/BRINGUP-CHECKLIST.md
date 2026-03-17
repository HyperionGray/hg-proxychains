# Bring-up checklist

## Smoke harness

- [ ] Clone private repo `P4X-ng/FunkyDNS` into `third_party/FunkyDNS`
- [ ] `docker compose build`
- [ ] `docker compose up`
- [ ] Confirm `client` prints `200 Connection Established`
- [ ] Confirm `client` receives `OK from exit-server`
- [ ] `curl http://localhost:9191/health`
- [ ] `curl -i http://localhost:9191/ready` returns HTTP 200
- [ ] Confirm hop probes are green or at least responding with expected policy/auth status

## Host deployment

- [ ] Create `egressd` host user
- [ ] Review `scripts/host-nftables.sh` for bridge name and infra CIDRs
- [ ] Review `scripts/host-egress-owner.sh` for upstream IP allowlist
- [ ] Install `pproxy`, `pyjson5`, and `egressd` files
- [ ] Install systemd unit from `egressd/systemd/egressd.service`
- [ ] Verify raw DNS to external resolvers is blocked from a workload
- [ ] Verify workload can only egress through local listener
- [ ] Verify only the `egressd` UID can reach configured upstream IPs
- [ ] Kill one upstream proxy and confirm fail-closed behavior
