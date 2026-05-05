# QUICKSTART

The shortest path from a fresh clone to running real programs through
the chain.

## 0) Prereqs

- `podman`
- `podman-compose`
- `python3` (for `pf.py`)

## 1) Bring up the chain

`./hg-proxychains up` and `make up` will try to bootstrap the missing
dependency automatically. If you want to do it yourself first:

```bash
./pf.py up --build
```

That builds and starts the three core services that make up the chain:

```text
client -> egressd -> proxy1 -> proxy2 -> internet
```

`egressd` is the local CONNECT listener; `proxy1` and `proxy2` are the
two upstream hops you can swap for your own.

The chain visual prints to stderr on first start and again on every
hop state change, exactly the way the original proxychains used to:

```text
[egressd] |S-chain|proxy1:3128<->proxy2:3128<->OK
[egressd]   hop_0: proxy1:3128                 OK   42ms
[egressd]   hop_1: proxy2:3128                 OK   38ms
```

## 2) Run a program through the chain

```bash
./pf.py run curl -fsS https://example.com
./pf.py run dig +short example.com
./pf.py run wget -qO- https://example.com
```

Or open an interactive shell where every command is forced through
the chain:

```bash
./pf.py shell
[chained:/work]$ curl -fsS https://example.com
[chained:/work]$ exit
```

The wrapper container uses `proxychains4` with `strict_chain` and
`proxy_dns`, so DNS lookups travel through the chain too. Direct
TCP and direct DNS are both blocked.

If you ever need to bypass the chain inside the wrapper (for
diagnostics), use `raw`:

```bash
./pf.py shell
[chained:/work]$ raw curl -fsS http://egressd:9191/health
```

## 3) Check status

```bash
./pf.py status
./pf.py logs -f
```

## 4) Tear it all down

```bash
./pf.py down -v
```

## 5) Optional: run the full smoke harness

The smoke harness adds FunkyDNS (DoH on 443), a `searchdns` helper,
and an `exitserver` so the run can prove the DoH and CONNECT-chain
properties end to end:

```bash
./pf.py bootstrap          # fetch third_party/FunkyDNS
./pf.py smoke --build      # one-shot run; exits with the test client
```

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

Then `./pf.py up --build` again.
