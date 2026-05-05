# QUICKSTART

Fastest complete path for a new user to get hg-proxychains running end to end.

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
[egressd] |S-chain|proxy1:3128<-->proxy2:3128<-->OK
```

## 3) Start the stack

```bash
podman-compose up --build
```

Or:

```bash
make smoke
```

You get a one-shot `client` container that runs:

```bash
hg-proxychains smoke
```

The wrapper talks to `egressd` and prints a proxychains-style chain view such as:

```text
[hg-proxychains] |S-chain|proxy1:3128<-->proxy2:3128<-->OK
```

To wrap your own command through the chain after the stack is up:

```bash
podman-compose run --rm client curl -fsS https://example.com/
# or
make run CMD="curl -fsS https://example.com/"
```

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

## 6) Correctness boundary

The compose topology puts `client` on an internal `worknet` with only `egressd`
and `funky`, while proxy hops and the exit server live on `proxynet`. That makes
the smoke workload fail closed for direct TCP egress and keeps smoke DNS pointed
at FunkyDNS. `chain.allowed_ports` is a config/readiness guard; runtime port
policy must be enforced by `egressd`/`pproxy` configuration or the host firewall
for production host deployments.

## 7) Troubleshooting

```bash
make logs
make health
make ready
```
