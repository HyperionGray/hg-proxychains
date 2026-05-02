# QUICKSTART

Fastest complete path for a new user to get this repo running end to end.

## 0) Prereqs

- `podman`
- `podman-compose`
- `python3`
- `make`

## 1) Initialize third-party dependency

```bash
git submodule update --init --recursive third_party/FunkyDNS
```

Or:

```bash
make deps
```

## 2) Minimal config (optional but recommended)

`egressd/config.json5` only needs your proxy list:

```json5
{
  proxies: [
    "http://proxy1:3128",
    "http://proxy2:3128"
  ],
  logging: {
    chain_visual: true
  }
}
```

`chain_visual: true` enables the classic chain view:

```text
[egressd] |S-chain|proxy1:3128<->proxy2:3128<->OK
```

## 3) Start chain stack (primary UX)

```bash
python3 scripts/hg_proxychains.py up --build
```

This waits for readiness and prints a proxychains-style chain line.

## 4) Run a wrapped command through the chain

```bash
python3 scripts/hg_proxychains.py run -- curl -fsS http://exitserver:9999/
```

Use `run` with any command (`curl`, `apt`, custom scripts, etc.). The command
runs inside the `runner` container with proxy env vars and DNS forced through
the stack.

## 5) Run full smoke verification (correctness pass)

```bash
python3 scripts/hg_proxychains.py smoke
```

Or:

```bash
make smoke
```

Wait for one-shot `client` completion. A healthy smoke run includes:

- `DNS OK` / `DoH OK` for `smoke.test`
- `DNS OK` / `DoH OK` for `hosts.smoke.internal`
- `DNS OK` / `DoH OK` for `printer`
- `CONNECT` followed by `OK from exit-server`

Then verify health endpoints:

```bash
curl -sk https://localhost:18443/healthz
curl http://localhost:9191/health
curl -f http://localhost:9191/ready
curl http://localhost:9191/live
```

## 6) Stop and clean up

```bash
python3 scripts/hg_proxychains.py down -v
```

Or:

```bash
make down
```

## 7) Troubleshooting

```bash
make logs
make health
make ready
```
