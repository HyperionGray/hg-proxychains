# egressd preflight validation

`egressd` now includes a preflight validator that checks configuration and
runtime prerequisites before the supervisor starts services.

## What it validates

- `listener.port` is a valid TCP port
- `chain.hops` is non-empty
- each hop URL uses `http` or `https` and includes a hostname
- `chain.canary_target` uses `host:port` format
- `supervisor.gateway_mode` is either `native` or `pproxy`
- `supervisor.pproxy_bin` exists and is executable / on `PATH` when `gateway_mode=pproxy`
- if `dns.launch_funkydns=true`:
  - `supervisor.funkydns_bin` exists and is executable / on `PATH`
  - `dns.port` is a valid TCP port

## How to run it

From the repo root:

```bash
make preflight
```

The Makefile target builds the `egressd` image and runs the supervisor in
`--check-config` mode with `EGRESSD_PREFLIGHT_SKIP_BIN_CHECKS=true`, so config
validation still works even when optional binaries like `pproxy` only exist
inside the container image.

For a full image-level validation with binary checks enabled:

```bash
make validate-config
```

Or directly:

```bash
python3 egressd/supervisor.py --check-config --config egressd/config.json5
```

The direct command requires local Python dependencies such as `pyjson5`.

The command prints a JSON report:

- `ok=true` means startup prerequisites passed
- `warnings` are advisory
- `errors` block startup and should be fixed

In native gateway mode, a missing `pproxy` binary is reported as a warning
instead of a hard error because the built-in CONNECT gateway can still run.

## Runtime behavior

When running normally (`python3 egressd/supervisor.py`), preflight runs at
startup. If there are blocking errors, the supervisor exits immediately instead
of entering a restart loop.
