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

### 1. Initialize FunkyDNS submodule

Configure authenticated GitHub access, then initialize the private submodule:

```bash
git submodule update --init --recursive third_party/FunkyDNS
```

If you prefer a direct clone workflow, you can still clone `P4X-ng/FunkyDNS`
into `third_party/FunkyDNS` manually:

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

- readiness endpoint:

```bash
curl -f http://localhost:9191/ready
```

## What the smoke harness proves

- local explicit CONNECT tunnel establishment
- multi-hop relay via `pproxy`
- end-to-end raw TCP after CONNECT
- per-hop health probes
- optional separate FunkyDNS service for DNS work

It does **not** prove host enforcement. For that, use the scripts in `scripts/` on a real Linux host and follow `docs/HOST-DEPLOYMENT.md`.

## Health vs readiness

- `GET /live`: process is up (simple liveness check)
- `GET /health`: detailed state (`pproxy`, `funkydns`, per-hop probe details, and readiness block)
- `GET /ready`: returns `200` only when `egressd` is usable for forwarding
  - `pproxy` must be running
  - if `dns.launch_funkydns=true`, FunkyDNS must also be running
  - hop checks must be complete and successful by default

Readiness behavior can be tuned via:

- `supervisor.ready_require_hops`
- `supervisor.ready_require_all_hops`

## Important split: smoke mode vs host mode

The compose harness runs FunkyDNS as a **separate service**.

`egressd` does **not** launch FunkyDNS in smoke mode. That avoids double-start bugs and keeps service boundaries clean.

For host mode, `egressd/config.host.example.json5` shows how to launch FunkyDNS locally if you want a single host-managed stack.

## What to tweak first

- `egressd/config.json5`: proxy hop URLs, canary target, health port
- `scripts/host-egress-owner.sh`: upstream proxy and DoH IPs
- `scripts/host-nftables.sh`: bridge interface name and infra CIDRs

## Notes on FunkyDNS review

I added a short review in `docs/FUNKYDNS-REVIEW.md` with the concrete issues worth fixing before you rely on it in a production-ish setup.
