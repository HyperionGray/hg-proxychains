# egressd starter repo

A small, fail-closed prototype for container egress enforced through chained HTTP CONNECT proxies.

This starter repo is split into two tracks:

- **Smoke harness**: docker-compose setup to prove the CONNECT chain works end to end.
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
│   └── HOST-DEPLOYMENT.md
├── egressd/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── chain.py
│   ├── supervisor.py
│   ├── config.json5
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
│   ├── host-nftables.sh
│   └── host-egress-owner.sh
└── third_party/
    └── README.md
```

## Quick start

### 1. Add FunkyDNS locally

Configure authenticated GitHub access, then clone the private
`P4X-ng/FunkyDNS` repository into `third_party/FunkyDNS`:

```bash
git clone https://github.com/P4X-ng/FunkyDNS.git third_party/FunkyDNS
```

### 2. Build and run the smoke harness

```bash
docker compose build
docker compose up
```

### 3. Check results

- `client` should print a successful `CONNECT` followed by `OK from exit-server`
- health endpoint:

```bash
curl http://localhost:9191/health
```

- readiness endpoint (returns `200` when ready, `503` when not ready):

```bash
curl -i http://localhost:9191/ready
```

## What the smoke harness proves

- local explicit CONNECT tunnel establishment
- multi-hop relay via `pproxy`
- end-to-end raw TCP after CONNECT
- per-hop health probes
- optional separate FunkyDNS service for DNS work

It does **not** prove host enforcement. For that, use the scripts in `scripts/` on a real Linux host and follow `docs/HOST-DEPLOYMENT.md`.

## Important split: smoke mode vs host mode

The compose harness runs FunkyDNS as a **separate service**.

`egressd` does **not** launch FunkyDNS in smoke mode. That avoids double-start bugs and keeps service boundaries clean.

For host mode, `egressd/config.host.example.json5` shows how to launch FunkyDNS locally if you want a single host-managed stack.

## What to tweak first

- `egressd/config.json5`: proxy hop URLs, canary target, health port
- `scripts/host-egress-owner.sh`: upstream proxy and DoH IPs
- `scripts/host-nftables.sh`: bridge interface name and infra CIDRs

## Health and readiness behavior

`egressd` now exposes two endpoints:

- `/health`: always returns `200` plus runtime state and computed readiness fields
- `/ready`: returns `200` only when the relay is ready, otherwise `503` with a reason

Readiness requires:

1. `pproxy` is currently running
2. hop checks exist and are fresh
3. all hops are healthy (unless disabled in config)

Tunable supervisor keys:

- `require_all_hops_healthy` (default `true`)
- `ready_grace_period_s` (default `max(hop_check_interval_s * 2, 5)`)
- `max_hop_status_age_s` (default `max(hop_check_interval_s * 3, 5)`)

## Notes on FunkyDNS review

I added a short review in `docs/FUNKYDNS-REVIEW.md` with the concrete issues worth fixing before you rely on it in a production-ish setup.
