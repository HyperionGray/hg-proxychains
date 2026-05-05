# QUICKSTART

The shortest path from a fresh clone to running real programs through
the chain.

## 0) Prereqs

- `podman`
- `podman-compose`
- `make` (only if you prefer `make` over the wrapper script)

## 1) Bring up the chain

```bash
./hg-proxychains up
```

That builds and starts the four core services:

```text
your program ──> client ──> egressd ──> proxy1 ──> proxy2 ──> internet
```

- `egressd` is the local CONNECT listener and chain supervisor
- `proxy1` and `proxy2` are the two upstream hops (swap them for
  your own)
- `client` is the locked-down workload container with `iptables` set
  to fail-closed and `HTTP_PROXY` env pointed at `egressd`. This is
  where your programs actually run.

The chain visual prints to stderr on first start and again on every
hop state change, exactly the way the original proxychains used to:

```text
[egressd] |S-chain|proxy1:3128<->proxy2:3128<->OK
[egressd]   hop_0: proxy1:3128                 OK   42ms
[egressd]   hop_1: proxy2:3128                 OK   38ms
```

## 2) Run a program through the chain

```bash
./hg-proxychains run -- curl -fsS https://example.com
./hg-proxychains run -- python3 -c "import urllib.request; print(urllib.request.urlopen('https://example.com').status)"
```

Or open an interactive shell:

```bash
./hg-proxychains shell
$ curl -fsS https://example.com
$ exit
```

The shell is not a magic "chained shell"; it is a normal bash inside
a container whose only outbound TCP path is `egressd`. Direct DNS or
non-proxied TCP connections are dropped by the iptables rules
installed at startup.

## 3) Check status

```bash
./hg-proxychains status
./hg-proxychains logs
```

`status` exec's `runner.py status` inside the client and also prints
the chain visual from `egressd /health`.

## 4) Tear it all down

```bash
./hg-proxychains down
```

That runs `compose down -v`, removing volumes too.

## 5) Optional: run the full smoke harness

The smoke harness adds FunkyDNS (DoH on 443), a `searchdns` helper,
and an `exitserver` so the run can prove the DoH and CONNECT-chain
properties end to end:

```bash
./hg-proxychains smoke
```

The first invocation runs `make deps` for you to fetch the
`third_party/FunkyDNS` submodule.

## 6) Use your own proxies

Edit `egressd/config.json5` and replace the proxy URLs:

```json5
{
  proxies: [
    "http://user:pass@proxy-a.example:3128",
    "http://user:pass@proxy-b.example:3128",
    "http://proxy-c.example:3128",
  ],
  chain: { canary_target: "proxy-a.example:3128" },
}
```

Then `./hg-proxychains down && ./hg-proxychains up` to apply.
