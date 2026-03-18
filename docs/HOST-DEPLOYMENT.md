# Host deployment notes

This repo's compose stack is only a smoke harness. Real enforcement happens on a Linux host with:

- a container bridge or netns boundary
- nftables TPROXY interception
- policy routing for marked packets
- a local `egressd` listener
- owner-based OUTPUT rules so only the `egressd` UID can talk to upstream proxies or DoH endpoints

## Recommended host sequence

1. Create a dedicated `egressd` user.
2. Install Python deps for `egressd`:
   - `pproxy`
   - `pyjson5`
3. Copy `egressd/` to `/opt/egressd`
4. Put a host config at `/etc/egressd/config.json5` based on `config.host.example.json5`
   - For embedded FunkyDNS, set `dns.doh_upstreams` to one or more DoH endpoints.
5. Run `scripts/host-nftables.sh`
6. Run `scripts/host-egress-owner.sh`
7. Install and start `egressd/systemd/egressd.service`
8. Validate readiness with `curl -f http://127.0.0.1:9191/ready`

## Runtime probes

- `GET /live` on the configured health bind/port for liveness.
- `GET /health` for full state (process state + hop status details).
- `GET /ready` for gating dependent services and automation. This returns non-200 when `pproxy` is down, FunkyDNS is required but not running, or hop checks fail (by default).

## Expected traffic model

workload -> local listener -> pproxy chain -> upstream proxy 1 -> upstream proxy 2 -> destination

DNS must go only to the local DoH-capable stub. Raw UDP/TCP 53 from workloads should be dropped.

## Readiness and startup gating

`egressd` supports fail-closed startup gating tied to hop checks:

- `supervisor.block_start_until_hops_healthy` (default `true` in examples):
  - when enabled, `pproxy` startup is delayed until hop probes meet policy
- `supervisor.require_all_hops_healthy`:
  - when `true`, every configured hop must be healthy for readiness
- `supervisor.max_hop_status_age_s`:
  - readiness fails when hop probe data goes stale

This allows stricter behavior on hosts where fail-closed semantics are required before accepting traffic.
