# wrapper/

Container that gives users the classic proxychains UX:

    proxy1 <-> proxy2 <-> proxy3

without DNS or TCP leakage. Inside the container, every program is
launched under `proxychains4 -q`, configured to send all DNS and TCP
through the local `egressd` CONNECT listener. `egressd` then handles
the actual multi-hop chain through the configured upstream proxies.

This container is the user-facing surface for `hg-proxychains run` and
`hg-proxychains shell` (see `pf.py` and `docs/cli/`). Do not put the
wrapping logic anywhere else.

Files:

- `Dockerfile`         small Debian-based image with proxychains4
- `proxychains4.conf`  forces strict_chain + proxy_dns
- `entrypoint.sh`      dispatches `shell|raw|<cmd>` modes

Notes:

- `proxy_dns` + `strict_chain` is what closes the DNS-leak hole; do
  not weaken these defaults without a security review.
- `raw <cmd>` is the diagnostic escape hatch and is the only way to
  bypass the chain inside the wrapper container.
- `HTTP_PROXY` env vars are also exported so well-behaved HTTP clients
  go through the chain even when proxychains4 cannot intercept (for
  example, Go static binaries).
