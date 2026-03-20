# Quick Start

Get egressd running quickly with the podman smoke harness.

## What this gives you

You will start a fail-closed egress proxy chain with DNS-over-HTTPS and verify:

- DNS resolution through the local resolver path
- CONNECT chain forwarding through multiple proxy hops
- supervisor health/readiness endpoints

## Prerequisites

- `podman`
- `podman-compose`
- GitHub access for `third_party/FunkyDNS` submodule checkout

## Start the stack

```bash
make deps
make smoke
```

## Verify success

Watch the `client` output for:

- `DNS OK` and `DoH OK` lines for the smoke domains
- `OK from exit-server` to confirm end-to-end CONNECT chain behavior

Then verify health/readiness:

```bash
curl http://localhost:9191/health | python3 -m json.tool
curl http://localhost:9191/ready
```

## Useful follow-up

- Full architecture and operational details: `README.md`
- Host nftables deployment flow: `docs/HOST-DEPLOYMENT.md`
- Maintenance and cleanup commands: `docs/REPO_MAINTENANCE.md`
