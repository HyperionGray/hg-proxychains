# Quick Start

Get egressd running in under 2 minutes.

## What is this?

A fail-closed container egress proxy chain with DNS-over-HTTPS. No direct DNS from workloads, all traffic forced through supervised HTTP CONNECT proxies.

## Prerequisites

- `podman`
- `podman-compose`
- GitHub access (for FunkyDNS submodule)

## Get Started

**1. Clone dependencies:**
```bash
make deps
```

**2. Run the smoke test:**
```bash
make smoke
```

**3. Watch for success:**

The `client` container will print:
- `DNS OK` and `DoH OK` for test domains
- `OK from exit-server` (proves end-to-end CONNECT chain works)

**4. Check health endpoints:**
```bash
curl http://localhost:9191/health | python3 -m json.tool
curl http://localhost:9191/ready
```

## Next Steps

- Read `README.md` for full details on configuration
- See `docs/HOST-DEPLOYMENT.md` for production host setup with nftables enforcement
- Tweak `egressd/config.json5` for your proxy chain and canary targets
