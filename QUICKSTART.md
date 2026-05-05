# QUICKSTART

Fastest complete path for a new user to get hg-proxychains running end to end.

## 0) Prereqs

- `podman`
- `podman-compose`
- `make`

## 1) Initialize third-party dependency

`./hg-proxychains up` and `make up` will try to bootstrap the missing
dependency automatically. If you want to do it yourself first:

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
make up
```

Or:

```bash
./hg-proxychains up
```

## 4) Run something through the chain

Once `client` prints its ready banner, run a command through the locked-down
client container:

```bash
./hg-proxychains run -- curl -s https://ifconfig.me
```

Or:

```bash
make run CMD="curl -s https://ifconfig.me"
```

You can also open an interactive shell:

```bash
./hg-proxychains shell
```

## 5) Run the smoke check

The end-to-end smoke test is still available, but it is no longer the default
thing that happens on every `compose up`:

```bash
./hg-proxychains smoke
```

Or:

```bash
make smoke
```

## 6) Confirm expected output

The wrapper prints a proxychains-style chain view such as:

```text
[hg-proxychains] |S-chain|proxy1:3128<-->proxy2:3128<-->OK
```

A healthy smoke run includes:

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

## 7) Stop and clean up

```bash
podman-compose down -v
```

Or:

```bash
make down
```

## 8) Correctness boundary

The compose topology puts `client` on an internal `worknet` with only `egressd`
and `funky`, while proxy hops and the exit server live on `proxynet`. That makes
the smoke workload fail closed for direct TCP egress and keeps smoke DNS pointed
at FunkyDNS. `chain.allowed_ports` is a config/readiness guard; runtime port
policy must be enforced by `egressd`/`pproxy` configuration or the host firewall
for production host deployments.

## 9) Troubleshooting

```bash
make logs
make health
make ready
```
