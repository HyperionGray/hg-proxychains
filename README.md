# egressd starter repo

A small, fail-closed prototype for container egress enforced through chained HTTP CONNECT proxies.

This starter repo is split into two tracks:

- **Smoke harness**: `podman-compose` setup to prove DoH and the CONNECT chain end to end.
- **Host deployment examples**: nftables + TPROXY + owner-gating scripts for a real host.

The design goal is intentionally boring:

- HTTP CONNECT everywhere
- no direct DNS from workloads
- DNS only through a local DoH-capable resolver
- fail closed
- simple supervision and observability first

## Repo layout

```text
.
├── README.md
├── Makefile
├── docker-compose.yml
├── docs/
│   ├── BRINGUP-CHECKLIST.md
│   ├── FUNKYDNS-REVIEW.md
│   ├── HOST-DEPLOYMENT.md
│   ├── REPO_MAINTENANCE.md
│   └── USER-FLOW-REVIEW.md
├── egressd/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── chain.py
│   ├── readiness.py
│   ├── supervisor.py
│   ├── test_supervisor.py
│   ├── config.json5
│   ├── config.simple.example.json5
│   ├── config.host.example.json5
│   └── systemd/egressd.service
├── proxy/
│   └── Dockerfile
├── exitserver/
│   ├── Dockerfile
│   └── echo_server.py
├── client/
│   ├── Dockerfile
│   └── test_client.py
├── scripts/
│   ├── bootstrap-third-party.sh
│   ├── host-nftables.sh
│   ├── repo_hygiene.py
│   ├── repo_maintenance.py
│   ├── host-egress-owner.sh
│   └── test_repo_hygiene.py
├── tests/
│   ├── test_readiness.py
│   └── test_supervisor.py
└── third_party/
    └── README.md
```

## Quick start

Start with `QUICKSTART.md` for the shortest smoke-harness path.
For a reviewed walkthrough of the smoke-harness flow, host flow, and current
known breakpoints, see `docs/USER-FLOW-REVIEW.md`.

## Minimal config

The only required setting is your list of proxies.  Everything else uses
safe, sensible defaults (fail-closed, DoH-only DNS, health endpoints on
port 9191, etc.):

```json5
// egressd/config.json5
{
  proxies: [
    "http://proxy1:3128",
    "http://proxy2:3128",
  ],
}
```

Plain URL strings and the canonical `{"url": "..."}` dict form are both
accepted.  See `egressd/config.simple.example.json5` for this minimal
format and `egressd/config.host.example.json5` for a fully-annotated host
deployment example.

### 1. Initialize FunkyDNS submodule

Configure authenticated GitHub access, then initialize the private submodule:

```bash
git submodule update --init --recursive third_party/FunkyDNS
```

If you prefer a direct clone workflow, you can still clone `P4X-ng/FunkyDNS`
into `third_party/FunkyDNS` manually:

```bash
make deps
```

This uses `scripts/bootstrap-third-party.sh`, which checks out the exact gitlink
revision for `third_party/FunkyDNS` and normalizes the remote URL after auth.

### 2. Build and run the smoke harness

```bash
podman-compose build
podman-compose up
```

Or through the task runner:

```bash
make smoke
```

### 4. Check results

- `client` should print matching `DNS OK` and `DoH OK` lines for:
  - `smoke.test -> 203.0.113.10`
  - `hosts.smoke.internal -> 198.51.100.21`
  - `printer -> 198.51.100.42 (owner printer.corp.test.)`
- `client` should then print a successful `CONNECT` followed by `OK from exit-server`
- `funky` exposes the smoke DoH listener on `https://localhost:18443`

```bash
curl -sk https://localhost:18443/healthz
curl http://localhost:9191/health
curl -f http://localhost:9191/ready
curl http://localhost:9191/live
```

## What the smoke harness proves

- HTTPS DoH listener on `funky:443`
- direct DNS and DoH lookup for `smoke.test -> 203.0.113.10`
- mounted hosts-file lookup for `hosts.smoke.internal -> 198.51.100.21`
- mounted `resolv.conf` search-domain lookup for `printer -> printer.corp.test -> 198.51.100.42`
- local explicit CONNECT tunnel establishment
- multi-hop relay via the native fail-closed CONNECT gateway
- end-to-end raw TCP after CONNECT
- per-hop health probes and readiness gating
- separate FunkyDNS and upstream search-DNS services for DNS work

The smoke config uses `exitserver:9999` as the canary target, so readiness does
not depend on external internet reachability.

It does **not** prove host enforcement. For that, use the scripts in `scripts/` on a real Linux host and follow `docs/HOST-DEPLOYMENT.md`.

## Health vs readiness

- `GET /live`: process is up (simple liveness check)
- `GET /health`: detailed state (`pproxy`, `funkydns`, per-hop probe details, and readiness block)
- `GET /ready`: returns `200` only when `egressd` is usable for forwarding
  - the local gateway listener must be running
  - if `dns.launch_funkydns=true`, FunkyDNS must also be running
  - hop checks must be complete and the end-to-end chain probe must succeed by default
  - auth-required or policy-denied CONNECT responses stay visible in `/health`, but keep `/ready` red

Readiness behavior can be tuned via:

- `supervisor.require_all_hops_healthy`
- `supervisor.max_hop_status_age_s`
- `supervisor.block_start_until_hops_healthy`

## Important split: smoke mode vs host mode

The compose harness runs FunkyDNS as a **separate service**.

`egressd` does **not** launch FunkyDNS in smoke mode. That avoids double-start bugs and keeps service boundaries clean.

`egressd` now defaults to `supervisor.gateway_mode: "native"`, which means the
local listener is first-party code that parses CONNECT, enforces
`chain.allowed_ports`, and then dials the configured HTTP proxy chain hop by
hop. `pproxy` remains available as an explicit fallback mode for operators who
want the older listener behavior.

The smoke FunkyDNS image carries a self-signed cert, a clean local zone, a
mounted `hosts` file, and a mounted `resolv.conf` so compose can health-check:

- direct DNS on `53`
- a real DoH POST on `443`
- local `/etc/hosts` resolution
- search-domain recursion via a dedicated internal `searchdns` service

The smoke image also uses a small local launcher to bound FunkyDNS teardown,
because the upstream server path does not currently shut down reliably on
container stop signals.

The vendored FunkyDNS resolver now honors local host resolution before external
upstreams:

- `/etc/hosts` is checked first for A and AAAA records
- local zone files are checked next
- the system resolver from `/etc/resolv.conf` is preferred before explicit
  upstreams
- single-label names use the system resolver's search domains

That makes Ubuntu-style `systemd-resolved` setups behave the way operators
usually expect. In containerized deployments, point FunkyDNS at a usable
`resolv.conf` if the container's default one references an unreachable loopback
stub.

For host mode, `egressd/config.host.example.json5` shows how to launch FunkyDNS locally if you want a single host-managed stack.

## Startup preflight checks

`egressd` validates config and runtime prerequisites before starting the local
gateway. If preflight fails, it exits non-zero and logs each specific failure
(for example: invalid hop URL, empty chain, or a required binary missing in
`supervisor.gateway_mode: "pproxy"`).

Useful checks:

```bash
make preflight
make validate-config
```

## What to tweak first

- `egressd/config.json5`: list your proxy hops under `proxies:`; all other fields are optional
- `egressd/config.simple.example.json5`: the absolute minimum — just a `proxies` list
- `egressd/config*.json5` DNS section: use `doh_upstreams` (list) or legacy `doh_upstream` (single URL)
- `scripts/host-egress-owner.sh`: upstream proxy / DoH IP allowlists, including optional IPv6 allowlists
- `scripts/host-nftables.sh`: bridge interface name, infra CIDRs, and whether IPv6 is explicitly enabled

## Chain visual

Set `logging.chain_visual: true` in your config to get a terminal-friendly
proxychains-style display on stderr.  It prints on startup (topology only)
and again whenever the per-hop health state changes:

```
[egressd] |S-chain|-<>-proxy1:3128-<>-proxy2:3128-<>-OK
[egressd]   hop_0: proxy1:3128                 OK   42ms
[egressd]   hop_1: proxy2:3128                 OK   38ms
```

When a hop is unreachable the connector flips to `-XX-` and the line ends
with `FAIL`:

```
[egressd] |S-chain|-<>-proxy1:3128-XX-proxy2:3128-<>-FAIL
[egressd]   hop_0: proxy1:3128                 OK   42ms
[egressd]   hop_1: proxy2:3128                 FAIL Connection refused
```

The visual is disabled by default (`logging.chain_visual: false`) so it does not
interfere with JSON log pipelines.

## Maintenance and cleanup

Run repository maintenance checks (unfinished markers, backup files, stale artifacts, stray cache dirs, and unexpected embedded git repos) for first-party code:

```bash
make maintenance
# equivalent: python3 scripts/repo_hygiene.py scan --repo-root .
```

For automatic cleanup of removable clutter (backup files, stray `__pycache__/` dirs, and known stale artifacts):

```bash
make maintenance-fix
# equivalent: python3 scripts/repo_hygiene.py clean --repo-root .
```

`maintenance*` targets focus on first-party code by default. For a full scan that
also includes `third_party/FunkyDNS`, use:

```bash
make maintenance-all
make maintenance-all-json
```

For scheduled automation, keep this check in the loop to catch new TODO/STUB markers and stray files early.

For focused first-party hygiene scans and stray cleanup:

```bash
make repo-scan
make repo-clean
make repo-scan-json
```

## Notes on FunkyDNS review

I added a short review in `docs/FUNKYDNS-REVIEW.md` with the concrete issues worth fixing before you rely on it in a production-ish setup.

## Maintenance helpers

- `make pycheck` compiles key Python entry points for syntax sanity.
- `make test` runs the repo's unit and hygiene checks.
- `make preflight` validates config in a disposable container with binary checks skipped.
- `make validate-config` validates the runtime image/config with normal binary checks.
- `make clean` removes local build/test artifacts (`__pycache__`, `.pytest_cache`, bundle tarball).
