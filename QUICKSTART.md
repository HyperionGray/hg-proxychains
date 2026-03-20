# Quick Start

## 1. Initialize dependencies

```bash
git submodule update --init --recursive third_party/FunkyDNS
```

## 2. Run the smoke harness

```bash
make smoke
# or: podman-compose up --build
```

## 3. Expected output from `client`

```
DNS OK: smoke.test A -> 203.0.113.10
DoH OK: smoke.test A -> 203.0.113.10
DNS OK: hosts.smoke.internal A -> 198.51.100.21
DoH OK: hosts.smoke.internal A -> 198.51.100.21
DNS OK: printer A -> 198.51.100.42 (owner printer.corp.test.)
DoH OK: printer A -> 198.51.100.42 (owner printer.corp.test.)
HTTP/1.1 200 Connection established
OK from exit-server
```

## 4. Health checks (while stack is running)

```bash
curl -f http://localhost:9191/ready    # 200 = egressd is ready
curl http://localhost:9191/health      # full JSON status
curl -sk https://localhost:18443/healthz  # FunkyDNS DoH
```

## 5. Run unit tests

```bash
make test
```

For host deployment, see `docs/HOST-DEPLOYMENT.md`.
For what the harness proves end to end, see `docs/USER-FLOW-REVIEW.md`.
