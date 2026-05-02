# hg-proxychains

A reboot of the classic [proxychains](https://github.com/rofl0r/proxychains-ng)
UX, but with the leak-prone bits removed and a sane container-first
deployment.

You bring up the chain. You run a program. The program's TCP and DNS
both go through the chain. That's it.

```text
your program ──> wrapper (proxychains4, no DNS leak) ──> egressd ──> proxy1 ──> proxy2 ──> internet
```

## Quick start (TL;DR)

```bash
./pf.py up                              # bring up the chain
./pf.py run curl -fsS https://example.com
./pf.py shell                           # interactive chained shell
./pf.py status                          # readiness + per-hop visual
./pf.py down -v                         # stop everything
```

See [`QUICKSTART.md`](QUICKSTART.md) for the longer walkthrough and
[`docs/cli/HG-PROXYCHAINS.md`](docs/cli/HG-PROXYCHAINS.md) for the
full CLI reference.

## What you actually get

- **`pf.py up`** — the only thing you need for day-to-day use. Brings
  up `proxy1`, `proxy2`, and `egressd`. Nothing else. No DNS infra,
  no smoke client.
- **`pf.py run <cmd>`** — runs `<cmd>` inside a wrapper container that
  uses `proxychains4` (`strict_chain`, `proxy_dns`) to force every TCP
  and DNS lookup through `egressd`. `egressd` then walks the chain
  through `proxy1 -> proxy2 -> ...`.
- **`pf.py shell`** — drops into an interactive shell where every
  command you run is automatically chained.
- **`pf.py status`** — pretty per-hop health view, classic
  proxychains style:

  ```text
  [egressd] |S-chain|proxy1:3128<->proxy2:3128<->OK
  [egressd]   hop_0: proxy1:3128                 OK   42ms
  [egressd]   hop_1: proxy2:3128                 OK   38ms
  ```

- **`pf.py smoke`** — runs the full DoH + CONNECT-chain smoke
  harness. This is the property test you only need when you change
  `egressd` or the FunkyDNS smoke image; you do not need to run it for
  normal use.

`pf.py` is the documented entry-point. The Makefile still exists and
calls the same things; use whichever you prefer.

## Repo layout

```text
.
├── README.md
├── QUICKSTART.md
├── pf.py                    # task runner & user-facing CLI
├── Makefile                 # thin wrapper around pf.py
├── docker-compose.yml
├── wrapper/                 # proxychains4 wrapper container ("pf run")
├── egressd/                 # local CONNECT listener + chain supervisor
├── proxy/                   # pproxy hop image (proxy1, proxy2)
├── exitserver/              # smoke-only echo target for the chain
├── client/                  # smoke-only DNS+CONNECT property test
├── funkydns-smoke/          # smoke-only DoH/DNS resolver
├── docs/
│   ├── cli/
│   │   └── HG-PROXYCHAINS.md
│   └── ...
├── scripts/
│   ├── bootstrap-third-party.sh
│   ├── repo_hygiene.py
│   └── ...
├── tests/
└── third_party/FunkyDNS/    # smoke-only submodule
```

## Configuration

The only required setting is your list of proxies. Defaults are
fail-closed and DoH-friendly:

```json5
// egressd/config.json5
{
  proxies: [
    "http://proxy1:3128",
    "http://proxy2:3128",
  ],
  chain: { canary_target: "proxy1:3128" },
}
```

Both plain URL strings and the canonical `{"url": "..."}` dict form
are accepted. See `egressd/config.simple.example.json5` for the
absolute minimum and `egressd/config.host.example.json5` for the
fully-annotated host deployment example.

## Health, readiness, and the chain visual

`egressd` exposes three HTTP endpoints on the supervisor port
(default `9191`, published on the host as `localhost:9191`):

- `GET /live` — process is up
- `GET /health` — full state (pproxy, funkydns, per-hop probes,
  readiness reasons)
- `GET /ready` — `200` only when `egressd` is usable for forwarding
  (pproxy running, hops healthy, hop probes fresh)

The chain visual is enabled by default in `egressd/config.json5` and
prints on every hop state change.

## Smoke harness (optional)

The smoke harness lives behind the `smoke` compose profile and
proves the DoH listener, hosts-file resolution, search-domain
recursion, and end-to-end CONNECT chain. It is *not* required for
normal use.

```bash
./pf.py bootstrap                  # fetch third_party/FunkyDNS once
./pf.py smoke --build              # one-shot run, exits with the client
```

A successful run prints matching `DNS OK` / `DoH OK` lines for
`smoke.test`, `hosts.smoke.internal`, and `printer`, followed by
`HTTP/1.1 200 Connection established` and `OK from exit-server`.

## Host deployment

The container UX is the recommended path. For a real Linux host with
nftables-enforced egress, see `docs/HOST-DEPLOYMENT.md`. The shape
is:

```text
local programs --(TPROXY/owner gate)--> egressd --> proxy1 --> proxy2 --> internet
```

`egressd/config.host.example.json5` is the fully-annotated config
template for that path.

## Tests and lints

```bash
./pf.py check          # py_compile + unit tests
./pf.py test           # unit tests only
./pf.py pycheck        # py_compile only
make preflight         # config validation in a disposable container
make validate-config   # config validation with full binary checks
```

## Maintenance

```bash
make repo-scan         # find TODO/STUB markers and stray files (first-party)
make repo-clean        # delete stray cache + backup files
make maintenance-all   # include third_party/FunkyDNS in the scan
```

## Related docs

- `QUICKSTART.md` — end-to-end happy path
- `docs/cli/HG-PROXYCHAINS.md` — CLI reference
- `docs/USER-FLOW-REVIEW.md` — design notes & smoke-harness review
- `docs/HOST-DEPLOYMENT.md` — host-mode deployment with nftables
- `docs/FUNKYDNS-REVIEW.md` — review of the vendored DNS resolver
