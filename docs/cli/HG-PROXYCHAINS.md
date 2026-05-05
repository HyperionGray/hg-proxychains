# `./hg-proxychains` CLI reference

`./hg-proxychains` is a small bash wrapper around `podman-compose` and
`compose exec`. It is the documented way to start the chain, run
programs through it, and tear it down. The Makefile targets delegate
to the same script.

There is no Python task runner. The wrapper is intentionally
under-engineered so the day-to-day commands stay stable across
upgrades.

## Synopsis

```
./hg-proxychains <command> [args]
```

## Common workflow

```bash
./hg-proxychains up                              # start the chain + locked-down client
./hg-proxychains run -- curl -fsS https://example.com
./hg-proxychains shell                           # interactive shell inside the client
./hg-proxychains status                          # /ready + per-hop visual
./hg-proxychains down                            # stop everything (and remove volumes)
```

## Commands

### `up`

Runs `compose up --build -d`. Brings up:

- `proxy1`, `proxy2` — the upstream HTTP CONNECT hops
- `egressd`           — the local CONNECT listener and chain supervisor
- `client`            — the locked-down workload container

The smoke services (`funky`, `searchdns`, `exitserver`) live behind
the `smoke` compose profile and are *not* started by `up`.

### `down`

Runs `compose down -v`. Stops the project and removes named volumes.

### `logs [SERVICE [args]]`

Runs `compose logs -f --tail=200`. With a service name, follows that
service only.

### `run -- <cmd> [args ...]`

`compose exec`s the given command inside the running `client`. The
`client` container has `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` env
vars pre-set to `http://egressd:15001` and a fail-closed `iptables`
configuration that only permits TCP to `egressd:15001` (plus DNS to
`funky` when the smoke profile is active).

```bash
./hg-proxychains run -- curl -fsS https://example.com
./hg-proxychains run -- pip install --upgrade requests
./hg-proxychains run -- env | grep -i proxy
```

The leading `--` is recommended but not required; it is there to
prevent your shell from interpreting flags meant for the inner
command.

### `shell [args ...]`

Opens an interactive bash inside the locked-down client. The shell
itself has no special prompt or wrapping; the leak prevention comes
from the iptables rules installed at startup, not from the shell.

```bash
./hg-proxychains shell
```

### `status`

Runs `runner.py status` inside the client. Prints:

- the proxy URL the client is locked to
- the DNS host the client is locked to (or `unconfigured` if the
  smoke profile is not active)
- whether the iptables firewall is in place

### `smoke`

Activates the `smoke` compose profile (`funky`, `searchdns`,
`exitserver`), brings everything up, then runs the end-to-end
property test inside the client. The first invocation also runs
`make deps` to fetch `third_party/FunkyDNS`.

You only need this if you are touching `egressd`, the FunkyDNS smoke
image, or the smoke-harness configuration.

## Environment variables

- `COMPOSE` — compose binary (default: `podman-compose`)
- `HG_PROXYCHAINS_CLIENT_SERVICE` — compose service to exec into
  (default: `client`); useful when running against a forked compose
  layout

## Exit codes

The wrapper propagates the exit code of the command it invokes.
`./hg-proxychains run -- <cmd>` returns the exit code of `<cmd>`.

## Why no Python task runner?

We do not ship a `pf.py`-style task runner because that ecosystem
([`pf-web-poly-compiler-runner-helper`](https://github.com/HyperionGray/pf-web-poly-compiler-runner-helper))
evolves on its own schedule. A wrapper that depends on it would
break every time the task grammar changed. The bash script and the
Makefile only depend on `compose` and the shell, both of which are
stable surfaces.
