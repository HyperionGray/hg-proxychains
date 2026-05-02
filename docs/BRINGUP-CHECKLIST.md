# Bring-up checklist

## Smoke harness

- [ ] Initialize submodule `third_party/FunkyDNS` (`git submodule update --init --recursive third_party/FunkyDNS`)
- [ ] `python3 scripts/hg_proxychains.py up --build`
- [ ] `python3 scripts/hg_proxychains.py run -- curl -fsS http://exitserver:9999/`
- [ ] Confirm wrapper prints a proxychains-style `<->` chain line with final `OK`
- [ ] `python3 scripts/hg_proxychains.py smoke`
- [ ] Confirm `client` prints `DNS OK: smoke.test A -> 203.0.113.10`
- [ ] Confirm `client` prints `DoH OK: smoke.test A -> 203.0.113.10 (owner smoke.test.)`
- [ ] Confirm `client` prints `DNS OK: hosts.smoke.internal A -> 198.51.100.21`
- [ ] Confirm `client` prints `DoH OK: hosts.smoke.internal A -> 198.51.100.21`
- [ ] Confirm `client` prints `DNS OK: printer A -> 198.51.100.42 (owner printer.corp.test.)`
- [ ] Confirm `client` prints `DoH OK: printer A -> 198.51.100.42 (owner printer.corp.test.)`
- [ ] Confirm `client` prints `HTTP/1.1 200 Connection established`
- [ ] Confirm `client` receives `OK from exit-server`
- [ ] `curl -sk https://localhost:18443/healthz`
- [ ] `curl -f http://localhost:9191/ready`
- [ ] `curl http://localhost:9191/health`
- [ ] `curl -i http://localhost:9191/ready` returns HTTP 200
- [ ] Confirm `searchdns` becomes healthy before `funky`
- [ ] Confirm hop probes show successful CONNECT responses for ready traffic; `403`/`407` should remain diagnostic-only failures in `/health`
- [ ] Confirm `client` starts only after `egressd` healthcheck is healthy

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
- [ ] Verify `/ready` transitions to failure when the proxy chain is unhealthy
