# QUICKSTART

Fastest path to verify the smoke harness end to end:

1. Initialize the private FunkyDNS submodule:
   ```bash
   git submodule update --init --recursive third_party/FunkyDNS
   ```
   If you prefer the helper script, run `make deps` instead.

2. Start the stack:
   ```bash
   podman-compose up --build
   ```
   Or run `make smoke`.

3. Wait for the one-shot `client` container to finish. A good run prints:
   - `DNS OK` / `DoH OK` for `smoke.test`
   - `DNS OK` / `DoH OK` for `hosts.smoke.internal`
   - `DNS OK` / `DoH OK` for `printer`
   - `CONNECT` followed by `OK from exit-server`

4. Spot-check health endpoints:
   ```bash
   curl -sk https://localhost:18443/healthz
   curl http://localhost:9191/health
   curl -f http://localhost:9191/ready
   ```

5. Tear it down when finished:
   ```bash
   podman-compose down -v
   ```
   Or run `make down`.

If anything looks off, use `make logs` and then read `README.md` or `docs/USER-FLOW-REVIEW.md` for the deeper walkthrough.
