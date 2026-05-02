# QUICKSTART

Fastest complete path for a new user to get this repo running end to end.

## 0) Prereqs

- `podman`
- `podman-compose`
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

## 3) Start smoke harness

Foreground (compose attaches; one-shot `client` runs when ready):

```bash
podman-compose up --build
```

Or:

```bash
make smoke
```

Background stack plus **your** command through the same chain as the smoke client (HTTP CONNECT via `egressd`, container DNS via `funky`):

```bash
./scripts/hg-proxychains daemon
./scripts/hg-proxychains run -- curl -fsS http://exitserver:9999/
```

Or the same via Make:

```bash
make smoke-daemon
make proxy-run ARGS='curl -fsS http://exitserver:9999/'
```

Stop background stack:

```bash
./scripts/hg-proxychains stop
# or: make smoke-down
```

The `|S-chain|proxy1:3128<->proxy2:3128<->OK` style line is printed on **egressd** stderr when hops change (`logging.chain_visual` in `egressd/config.json5`). Follow it with `./scripts/hg-proxychains logs` or `make logs`.

## 4) Confirm expected output

Wait for one-shot `client` completion. A healthy run includes:

- `DNS OK` / `DoH OK` for `smoke.test`
- `DNS OK` / `DoH OK` for `hosts.smoke.internal`
- `DNS OK` / `DoH OK` for `printer`
- `CONNECT` followed by `OK from exit-server`
- health endpoints responding (`/healthz`, `/health`, `/ready`, `/live`)

Then verify health endpoints:

```bash
curl -sk https://localhost:18443/healthz
curl http://localhost:9191/health
curl -f http://localhost:9191/ready
curl http://localhost:9191/live
```

## 5) Stop and clean up

```bash
podman-compose down -v
```

Or:

```bash
make down
```

## 6) Troubleshooting

```bash
make logs
make health
make ready
```
