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
5. Run `scripts/host-nftables.sh`
6. Run `scripts/host-egress-owner.sh`
7. Install and start `egressd/systemd/egressd.service`
8. Verify liveness and readiness:
   - `curl http://127.0.0.1:9191/health`
   - `curl -i http://127.0.0.1:9191/ready`

## Expected traffic model

workload -> local listener -> pproxy chain -> upstream proxy 1 -> upstream proxy 2 -> destination

DNS must go only to the local DoH-capable stub. Raw UDP/TCP 53 from workloads should be dropped.

## Readiness semantics

`/health` is liveness-only and always returns process state.

`/ready` returns `200` only when:

- `pproxy` is running
- hop checks are present and not stale
- every hop probe is healthy
- `funkydns` is running when `dns.launch_funkydns` is enabled

You can tune staleness with `supervisor.hop_status_ttl_s` (default: `max(15, hop_check_interval_s * 3)`).
