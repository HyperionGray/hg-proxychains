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

   If `172.18.0.0/16` conflicts with an existing bridge on your host, choose an
   alternate subnet before starting the stack. Example:

   ```bash
   export SMOKE_SUBNET=172.29.0.0/16
   export SMOKE_GATEWAY=172.29.0.1
   export SMOKE_SEARCHDNS_IP=172.29.0.40
   export SMOKE_FUNKY_IP=172.29.0.10
   export SMOKE_PROXY1_IP=172.29.0.11
   export SMOKE_PROXY2_IP=172.29.0.12
   export SMOKE_EXITSERVER_IP=172.29.0.20
   export SMOKE_EGRESSD_IP=172.29.0.5
   export SMOKE_CLIENT_IP=172.29.0.30
   export DNS_SERVER=funky
   podman-compose up
   ```

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

If your VM or kernel cannot provide the container-network firewall hooks that
Podman expects, you can still validate the first-party gateway and health flow
without containers:

```bash
make local-smoke
```

If anything looks off, use `make logs` and then read `README.md` or `docs/USER-FLOW-REVIEW.md` for the deeper walkthrough.
