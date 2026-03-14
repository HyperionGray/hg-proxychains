# egressd preflight validation

`egressd` now includes a preflight validator that checks configuration and
runtime prerequisites before the supervisor starts services.

## What it validates

- `listener.port` is a valid TCP port
- `chain.hops` is non-empty
- each hop URL uses `http` or `https` and includes a hostname
- `chain.canary_target` uses `host:port` format
- `supervisor.pproxy_bin` exists and is executable / on `PATH`
- if `dns.launch_funkydns=true`:
  - `supervisor.funkydns_bin` exists and is executable / on `PATH`
  - `dns.port` is a valid TCP port

## How to run it

From the repo root:

```bash
make preflight
```

Or directly:

```bash
python3 egressd/supervisor.py --check-config --config egressd/config.json5
```

The command prints a JSON report:

- `ok=true` means startup prerequisites passed
- `warnings` are advisory
- `errors` block startup and should be fixed

## Runtime behavior

When running normally (`python3 egressd/supervisor.py`), preflight runs at
startup. If there are blocking errors, the supervisor exits immediately instead
of entering a restart loop.
