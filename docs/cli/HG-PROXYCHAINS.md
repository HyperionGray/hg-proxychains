# `pf.py` / hg-proxychains CLI

`pf.py` is the user-facing entry-point. It is the documented way to
start, run programs through, and tear down the chain. Internally it
is a thin dispatcher over `podman-compose` and a few small helpers.

The Makefile targets shell out to the same primitives, so you can use
either; `pf.py` is the form that keeps working when you take the
project somewhere without GNU Make.

## Synopsis

```
pf <subcommand> [args]
```

## Common workflow

```bash
pf up                                # start the chain
pf run curl -fsS https://example.com # run a program through the chain
pf shell                             # interactive chained shell
pf status                            # /ready + /health
pf down -v                           # stop everything (and remove volumes)
```

## Subcommands

### `pf up [--build]`

Brings up the chain services in the background:

- `proxy1`, `proxy2` — the upstream hops (swap them for your own)
- `egressd`           — the local CONNECT listener and supervisor

`--build` rebuilds the images before starting them.

This subcommand intentionally does **not** start the smoke services
(`funky`, `searchdns`, `exitserver`, `client`) or the wrapper. The
wrapper is started on demand by `pf run` / `pf shell`. The smoke
services are gated behind the `smoke` compose profile.

### `pf down [-v]`

Stops the compose project. With `-v`, also removes named volumes.

### `pf logs [-f] [--tail N] [SERVICE ...]`

Tails the logs from the chain services (`proxy1`, `proxy2`, `egressd`)
by default, or from the listed services if any. `-f` follows.

### `pf run <cmd> [args ...]`

Runs `<cmd>` inside the wrapper container. The wrapper invokes
`proxychains4 -q` so all TCP and DNS lookups are pushed through
`egressd:15001` (which then walks the proxy chain).

```bash
pf run curl -fsS https://example.com
pf run dig +short example.com
pf run ssh -o ConnectTimeout=5 user@host.internal
```

The wrapper container has a small Debian-based userland with `curl`,
`wget`, `dig`, `ping`, `nc`, and friends. For anything else, mount
your binary or extend `wrapper/Dockerfile`.

### `pf shell`

Opens an interactive bash inside the wrapper. The prompt is
`[chained:CWD]$` so you cannot mistake it for a non-chained shell.
Every command you launch is forced through the chain.

Inside the chained shell, two helpers are available:

- `raw <cmd>` — bypass `proxychains4` (escape hatch for diagnostics)
- `pc <cmd>`  — explicitly invoke `proxychains4` (the default already
  applies, but useful when chaining flags through `bash -c`)

### `pf status`

Prints `/ready` followed by `/health` from `egressd` on
`http://localhost:9191`. Use this to confirm the chain is fully up
before you pour traffic through it.

### `pf health` / `pf ready`

Same as `pf status`, but only one endpoint each. Convenient for
scripting.

### `pf smoke [--build]`

Runs the full DoH + CONNECT smoke harness. This brings up the smoke
profile services (FunkyDNS, search DNS, exit server) and waits for
the one-shot `client` container to exit. The exit code of the harness
is the exit code of the client.

You only need this if you are touching `egressd`, the FunkyDNS smoke
image, or the smoke-harness configuration. `pf smoke` does require
the `third_party/FunkyDNS` submodule; run `pf bootstrap` once to
fetch it.

### `pf bootstrap`

Initialises `third_party/FunkyDNS`. Required only for the smoke
harness. `pf up` does not need it.

### `pf test`

Runs the unit tests (egressd supervisor, preflight, hop connectivity,
chain visual, compose layout, wrapper, CLI parser, repo hygiene).
This does not start any containers.

### `pf pycheck`

Runs `python3 -m py_compile` over every first-party Python entry-point.

### `pf check`

`pycheck` followed by `test`.

## Environment variables

- `HG_COMPOSE` — compose binary (default: `podman-compose`)
- `HG_PYTHON`  — python binary used by `pf test` and `pf pycheck`
  (default: the interpreter that launched `pf.py`)
- `HG_HEALTH_URL` — base URL for `pf health` / `pf ready` / `pf status`
  (default: `http://localhost:9191`)

## Exit codes

`pf.py` propagates the exit code of the command it invokes. `pf run
<cmd>` returns the exit code of `<cmd>` after `proxychains4` is done
with it.
