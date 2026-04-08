{
  "groups": [
    {
      "name": "Code organization & cleanup",
      "rules": [
        "Move all demo code/data to demo/ and never use in production.",
        "Mark demo runs with a large DEMO banner.",
        "Docs go in docs/ with clear subdirs.",
        "First task in every task list: 'clean up this directory'.",
        "Keep imports working; remove dead/unimplemented code."
      ]
    },
    {
      "name": "Data modeling & database",
      "rules": [
        "Prefer simple key-value stores for common needs.",
        "Choose high-cardinality partition keys (userId/tenantId/deviceId).",
        "Minimize cross-partition queries; use hierarchical partition keys to scale and target queries.",
        "Ensure even partition distribution."
      ]
    },
    {
      "name": "SDK & reliability",
      "rules": [
        "Use latest Cosmos DB SDK and async APIs when available.",
        "Reuse a singleton client; enable retries and preferred regions.",
        "Handle 429 with retry-after logic and log diagnostics for unexpected latency/status codes."
      ]
    },
    {
      "name": "Tools & containers",
      "rules": [
        "Use podman (not docker).",
        "Prefer plocate or fdfind over find.",
        "Use VMKit where applicable.",
        "Test every pf/pf.py entry before finishing work."
      ]
    },
    {
      "name": "Build & automation",
      "rules": [
        "Prefer pf.py as the task runner; keep pf scripts simple and delegate complexity to helpers.",
        "If AUTOMATION.txt exists: keep building until it's removed; first task: check AUTOMATION.txt; last task: plan next task."
      ]
    },
    {
      "name": "Testing & web",
      "rules": [
        "Prefer Playwright for web tests; validate every page and detect HTTP errors (502/404).",
        "Include file-upload tests where applicable."
      ]
    },
    {
      "name": "Python & environments",
      "rules": [
        "Prefer a conda environment; avoid hardcoded paths like /home/punk/.venv.",
        "Use CONDA_PREFIX/bin for full paths when needed; consider venv breaks from sudo."
      ]
    },
    {
      "name": "Style & output",
      "rules": [
        "Use only ASCII skulls as emojis (☠) if any; avoid other emojis.",
        "Prefer simple, clear, undecorated output for readability."
      ]
    },
    {
      "name": "Workflow & execution",
      "rules": [
        "Gather context before work: check WARP.md, PROJECT.txt, AGENTS.md, and .pf files.",
        "Use planfile.json for complex multi-part runs."
      ]
    },
    {
      "name": "Quality & restrictions",
      "rules": [
        "No demo code in production; run only production or real tests.",
        "Log and monitor diagnostics; tune RUs and retry strategies as needed."
      ]
    },
    {
      "name": "Metrics",
      "rules": [
        "Track CPUpwn (CPU-relative performance) for performance changes in any pcpu-related repo."
      ]
    }
  ],
  "precedence_note": "Rules in ascending order of precedence; later rules override earlier ones; project/subdirectory rules override parent/personal rules."
}

## Cursor Cloud specific instructions

### Overview

egressd is a fail-closed container egress enforcement system using chained HTTP CONNECT proxies. It is a pure Python project with Docker/Compose-based smoke tests.

### Running lint and tests (host-only, no containers)

- Activate the venv: `source /workspace/.venv/bin/activate`
- `make pycheck` -- syntax-checks all Python entry points
- `make test` -- runs unit tests (95/98 pass; 3 pre-existing failures on main)
- `make check` -- combined pycheck + test

### Running the smoke harness (full stack)

The Makefile defaults to `podman-compose`, but the Cloud VM has Docker. Override with:
```
make smoke COMPOSE="docker compose"
```
Or equivalently: `docker compose up --build`

Tear down: `docker compose down -v`

### Docker-in-Docker gotchas

The Cloud Agent VM runs inside a Firecracker container. Docker must use `fuse-overlayfs` storage driver (not overlay2), which is configured in `/etc/docker/daemon.json`. The iptables must be set to legacy mode. The `start.sh` script starts the Docker daemon but the fuse-overlayfs and iptables-legacy setup must be done once via the install script.

### Health endpoints (when smoke stack is running)

- `curl http://localhost:9191/health` -- detailed health
- `curl http://localhost:9191/ready` -- 200 when forwarding-ready
- `curl http://localhost:9191/live` -- liveness probe
- `curl -sk https://localhost:18443/healthz` -- FunkyDNS DoH health

### Known issues

- The FunkyDNS submodule at its pinned commit does not support `--no-system-resolver`, `--no-hosts-file`, hosts-file resolution via env vars, or resolv.conf search-domain expansion. Zone file fallbacks were added for `hosts.smoke.internal` and `corp.test` to work around this.
- The `printer` single-label search-domain resolution test in the client still fails (NXDOMAIN) because search-domain expansion requires FunkyDNS to read resolv.conf, which it does not.
