# hg-proxychains

A reboot of the classic [proxychains](https://github.com/rofl0r/proxychains-ng)
UX, but with the leak-prone bits removed and a sane container-first
deployment.

You bring up the chain. You run a program. The program's TCP and DNS
both go through the chain. That's it.

```text
your program ──> client (locked-down, fail-closed) ──> egressd ──> proxy1 ──> proxy2 ──> internet
```

## Quick start (TL;DR)

```bash
./hg-proxychains up                                # bring up the chain + locked-down client
./hg-proxychains run -- curl -fsS https://example.com
./hg-proxychains shell                             # interactive shell inside the locked-down client
./hg-proxychains status                            # /ready + per-hop visual
./hg-proxychains down                              # stop everything
```

See [`QUICKSTART.md`](QUICKSTART.md) for the longer walkthrough and
[`docs/cli/HG-PROXYCHAINS.md`](docs/cli/HG-PROXYCHAINS.md) for the
full CLI reference.

## What you actually get

`./hg-proxychains` is a small shell wrapper around `podman-compose`.
It has no opinions beyond what compose already does for you; we
explicitly avoid pulling in larger task-runner ecosystems so the
day-to-day commands are stable and obvious. The Makefile delegates
here too, so `make up` / `make run CMD="..."` / `make smoke` all work.

- **`up`** — brings up `proxy1`, `proxy2`, `egressd`, and the
  locked-down `client`. The `client` container has `iptables OUTPUT
  DROP` everywhere except a single hole to `egressd:15001`, plus
  `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` env vars pointed at
  `egressd`. Direct TCP outside the chain is dropped at the kernel.
- **`run -- <cmd>`** — `compose exec`s `<cmd>` inside the running
  `client`. The chain's fail-closed iptables rules and proxy env
  vars are already in place, so `curl`, `wget`, `pip`, `apt`, and
  any other proxy-aware tool routes through `egressd` automatically.
- **`shell`** — interactive bash inside the locked-down client.
- **`status`** — proxychains-style per-hop visual:

  ```text
  [hg-proxychains] |S-chain|proxy1:3128<-->proxy2:3128<-->OK
  ```

- **`smoke`** — activates the `smoke` profile (FunkyDNS DoH,
  search-DNS helper, echo exit server) and runs the end-to-end
  property test inside `client`. Only needed when you change
  `egressd` or the FunkyDNS smoke image.

## Repo layout

```text
.
├── README.md
├── QUICKSTART.md
├── hg-proxychains           # the shell wrapper (the CLI)
├── Makefile                 # thin delegate to ./hg-proxychains
├── docker-compose.yml
├── client/                  # locked-down workload container
│                            #   runner.py:        firewall + serve loop
│                            #   hg_proxychains.py: in-container run/smoke helpers
├── egressd/                 # local CONNECT listener + chain supervisor
├── proxy/                   # pproxy hop image (proxy1, proxy2)
├── exitserver/              # smoke-only echo target
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
prints on every hop state change. `./hg-proxychains status` renders
the same thing client-side.

## Smoke harness (optional)

The smoke harness lives behind the `smoke` compose profile and
proves the DoH listener, hosts-file resolution, search-domain
recursion, and end-to-end CONNECT chain. It is *not* required for
normal use.

```bash
./hg-proxychains smoke
```

A successful run prints matching `DNS OK` / `DoH OK` lines for
`smoke.test`, `hosts.smoke.internal`, and `printer`, followed by
`HTTP/1.1 200 Connection established` and `OK from exit-server`.

The smoke harness is the only thing that needs the FunkyDNS submodule;
`./hg-proxychains smoke` runs `make deps` for you the first time.

## Host deployment

The container UX is the recommended path. For a real Linux host with
nftables-enforced egress, see `docs/HOST-DEPLOYMENT.md`. The shape is:

```text
local programs --(TPROXY/owner gate)--> egressd --> proxy1 --> proxy2 --> internet
```

`egressd/config.host.example.json5` is the fully-annotated config
template for that path.

## Tests and lints

```bash
make check           # py_compile + unit tests
make test            # unit tests only
make pycheck         # py_compile only
make preflight       # config validation in a disposable container
make validate-config # config validation with full binary checks
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
