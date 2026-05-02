# User Flow Review

Review date: 2026-05-02

## Scope

This review covers:

- the compose-up flow driven by `docker-compose.yml`
- the runtime traffic path from the locked-down `client` runner to `exitserver`
- the explicit smoke-check flow driven by `./hg-proxychains smoke`
- health and readiness behavior exposed by `egressd`
- the operator-facing host deployment flow documented in `docs/HOST-DEPLOYMENT.md`

## Current Status

The broken `egressd` startup path found during the initial review has been
repaired.

Current state after the fix:

- the `egressd` image includes all runtime modules it imports
- `egressd/supervisor.py` now has one health/readiness implementation
- preflight is wired into both `--check-config` and normal startup
- unit tests and Make targets match the live supervisor API
- the smoke FunkyDNS image now starts DoH with an explicit self-signed cert
- the vendored FunkyDNS server now disables DoH and DoT when TLS files are
  missing and auto-cert is off
- the vendored FunkyDNS resolver now honors `/etc/hosts` and the system
  resolver defined by `resolv.conf` before falling back to explicit upstreams
- the smoke harness now mounts custom `hosts` and `resolv.conf` fixtures and
  proves that behavior over both DNS and DoH
- the smoke harness was re-run successfully end to end

## Smoke Harness Flow

### 1. Operator startup flow

1. Initialize `third_party/FunkyDNS`.
2. Run `podman-compose up --build` or `make up`.
3. Wait for `searchdns` to become healthy and answer `printer.corp.test`.
4. Wait for `proxy1`, `proxy2`, `exitserver`, and `funky` to become healthy.
5. `funky` becomes healthy only after direct DNS and DoH checks prove:
   - local zone resolution for `smoke.test`
   - mounted hosts-file resolution for `hosts.smoke.internal`
   - mounted `resolv.conf` search-domain resolution for `printer`
6. Wait for `egressd` to become healthy by passing its `/ready` healthcheck.
7. Compose starts the long-running `client` runner only after `egressd` is ready.
8. The `client` runner resolves the local DNS/proxy addresses, installs an
   OUTPUT-only firewall that permits only:
   - DNS to `funky:53`
   - CONNECT traffic to `egressd:15001`
   - loopback and established return traffic
9. The operator now uses `./hg-proxychains run -- <cmd>`, `shell`, or `smoke`.

### 2. Request flow

There are now two request paths:

#### a) Default compose-up path

1. The operator starts the stack.
2. The long-running `client` runner installs its local firewall and waits.
3. The operator runs `./hg-proxychains run -- <cmd>`.
4. The helper executes that command inside `client` with:
   - `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` set to `http://egressd:15001`
   - the local firewall already restricting traffic to only DNS + local egressd
5. The command's TCP egress path is therefore:
   `client -> egressd -> proxy1 -> proxy2 -> exitserver`

#### b) Explicit smoke path

When the stack is healthy, `./hg-proxychains smoke` does four groups of checks:

1. Query `smoke.test A` over direct DNS to `funky:53`.
2. Query `smoke.test A` over DoH to `https://funky/dns-query`.
3. Query `hosts.smoke.internal A` over direct DNS and DoH and expect the
   mounted hosts-file answer `198.51.100.21`.
4. Query `printer A` over direct DNS and DoH and expect the answer owner to be
   `printer.corp.test.` with value `198.51.100.42`, proving search-domain
   recursion from the mounted `resolv.conf`.
5. Open a TCP connection to `egressd:15001`.
6. Send `CONNECT exitserver:9999 HTTP/1.1`.
7. Expect a successful CONNECT response.
8. Send `GET /` through the established tunnel.
9. Print the response body returned by `exitserver`.

The intended paths are:

- `client -> funky` for direct DNS and DoH ingress checks
- `funky -> searchdns` for the single-label search-domain expansion path
- `client -> egressd -> proxy1 -> proxy2 -> exitserver` for the CONNECT proof

The observed success signal from the smoke run was:

- `DNS OK: smoke.test A -> 203.0.113.10 (owner smoke.test.)`
- `DoH OK: smoke.test A -> 203.0.113.10 (owner smoke.test.)`
- `DNS OK: hosts.smoke.internal A -> 198.51.100.21 (owner hosts.smoke.internal.)`
- `DoH OK: hosts.smoke.internal A -> 198.51.100.21 (owner hosts.smoke.internal.)`
- `DNS OK: printer A -> 198.51.100.42 (owner printer.corp.test.)`
- `DoH OK: printer A -> 198.51.100.42 (owner printer.corp.test.)`
- `HTTP/1.1 200 Connection established`
- `OK from exit-server`

### 3. Readiness flow

`docker-compose.yml` uses `egressd` `/ready` as the health gate that controls
whether the client runner is allowed to start.

Current readiness behavior:

- `pproxy` must be running
- hop checks must exist and be fresh
- all configured hops must be healthy by default
- managed FunkyDNS must be running when `dns.launch_funkydns=true`

In smoke mode, the canary target is `exitserver:9999`, so readiness remains
self-contained and does not depend on public internet access.

### 4. FunkyDNS behavior in smoke mode

The smoke harness still runs FunkyDNS as a separate service, but `egressd`
does not launch it internally in smoke mode.

Important nuance:

- the smoke image now installs `aiosqlite`, which was required for startup
- the smoke image now ships an explicit self-signed cert and key for DoH
- the smoke image now uses an isolated local zone directory with only
  `smoke.test A 203.0.113.10`
- the smoke image now mounts a custom `hosts` file and `resolv.conf`
- the smoke harness now runs a separate `searchdns` helper for the
  search-domain answer source
- the smoke healthcheck now runs direct DNS and real HTTPS DoH queries against
  the mounted-file and search-domain cases
- the smoke image now uses a small local launcher to bound FunkyDNS shutdown

The explicit smoke cert remains necessary because this harness intentionally
proves a working DoH listener on `443`. The local launcher remains necessary
because the current upstream signal handling still does not stop reliably in
the containerized smoke path.

## Host Deployment Flow

The documented host sequence is still:

1. Create a dedicated `egressd` user.
2. Install Python dependencies and copy the `egressd` files to the host.
3. Create `/etc/egressd/config.json5` from `egressd/config.host.example.json5`.
4. Apply nftables interception with `scripts/host-nftables.sh`.
5. Apply owner-based upstream restrictions with `scripts/host-egress-owner.sh`.
6. Install and start `egressd/systemd/egressd.service`.
7. Validate `http://127.0.0.1:9191/ready`.

This path was documented and code-traced in this review, but it was not
executed on a real host during this turn.

Important host-resolution note:

- local A and AAAA answers from `/etc/hosts` now win before zone files and
  upstream recursion
- names not found locally are sent to the system resolver loaded from
  `/etc/resolv.conf`
- single-label names such as `printer` use the search domains configured in
  that resolver, which matches common Ubuntu `systemd-resolved` behavior
- if you run FunkyDNS in a container and its `resolv.conf` points at an
  unreachable loopback stub, you need to supply a usable `resolv.conf` path or
  disable the system-resolver path

## Verification

The following checks passed:

- `python3 -m py_compile egressd/supervisor.py egressd/chain.py egressd/readiness.py egressd/preflight.py egressd/test_supervisor.py egressd/test_supervisor_readiness.py client/test_client.py exitserver/echo_server.py`
- `python3 -m py_compile funkydns-smoke/check_resolution.py funkydns-smoke/generate_cert.py funkydns-smoke/run_funkydns.py client/test_client.py third_party/FunkyDNS/funkydns/cli.py`
- `third_party/FunkyDNS/venv/bin/python -m unittest dns_server.tests.test_local_resolution dns_server.tests.test_tls_cert_handling`
- `python3 -m unittest egressd/test_supervisor_readiness.py`
- `python3 -m unittest egressd/test_supervisor.py`
- `python3 -m unittest tests/test_readiness.py`
- `python3 -m unittest tests/test_supervisor.py`
- `python3 -m unittest scripts/test_repo_hygiene.py`
- `make test`
- `make preflight`
- `make validate-config`
- `podman-compose up --build`
- `./hg-proxychains smoke`

## Residual Caveats

- upstream FunkyDNS still does not stop reliably on container stop signals in
  this environment, which is why the smoke image uses a local launcher wrapper.
- The compose harness now provides strong containment only for traffic that runs
  inside the `client` container through `./hg-proxychains run|shell|smoke`.
  It does not magically sandbox arbitrary host processes.
- Host-mode nftables and owner-gating were not executed in this turn, so host
  enforcement remains code-reviewed rather than runtime-proven here.

## Next Task

If you want the next improvement after this repair, the most useful one is
still to patch the upstream FunkyDNS signal-handling behavior so the smoke
image no longer needs the local launcher wrapper for bounded shutdown.
