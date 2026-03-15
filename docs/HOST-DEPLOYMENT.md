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
8. Verify `curl -f http://127.0.0.1:9191/ready` returns HTTP 200

## Expected traffic model

workload -> local listener -> pproxy chain -> upstream proxy 1 -> upstream proxy 2 -> destination

DNS must go only to the local DoH-capable stub. Raw UDP/TCP 53 from workloads should be dropped.

## Readiness semantics

`egressd` exposes:

- `/health`: process state snapshot (always 200 if the health server is up)
- `/ready`: returns 200 only if startup preflight checks passed, `pproxy` is running,
  and all currently probed hops are healthy; otherwise returns 503
