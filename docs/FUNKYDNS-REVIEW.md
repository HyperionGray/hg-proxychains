# FunkyDNS review notes

These are the concrete issues worth fixing before leaning on FunkyDNS harder.

## 1. Dependency manifests are inconsistent

### Why it matters

Packaging and runtime can drift. A fresh install may miss a dependency the code/docs expect, or install dependencies the docs call optional.

### Evidence to review

- `requirements.txt`
  - `aiohttp` appears with the note `# For HTTP async client`
  - `aiosqlite` is labeled optional
- `setup.py`
  - `aiohttp` is missing from `install_requires`
  - `aiosqlite` is present in `install_requires`
- Fast references from the repo snapshots I reviewed:
  - `requirements.txt`: lines 10-20
  - `setup.py`: lines 24-38

### Suggested fix

Make `requirements.txt`, `setup.py`, and docs tell the same story.

## 2. Production and attack modes live in the same package + CLI

### Why it matters

Even if the code is stable, this is a packaging and operational foot-gun. It increases the chance of wrong-mode deployment, reputation issues, and accidental exposure of features that should never be in the same runtime path as a clean resolver.

### Evidence to review

- README documents both `funkydns server` and `funkydns attack`
- package description in `setup.py` includes both production DNS and penetration testing capabilities
- Fast references:
  - `README.md`: lines 31-50 and 69-87
  - `setup.py`: lines 15-18

### Suggested fix

Split clean resolver and attack tooling into separate packages, entry points, or at least separate extras and docker images.

## 3. Admin token is generated at startup and logged

### Why it matters

That is convenient in a lab and annoying in any environment with central logs, retained journals, or broad log access.

### Evidence to review

- README admin API section says the admin token is generated at startup and logged
- Fast reference: `README.md` lines 312-364

### Suggested fix

Support explicit token provisioning, secret-file loading, or one-time bootstrap flow without logging the token.

## 4. Scripted zones execute embedded Python

### Why it matters

This is powerful, but it turns zone content into code execution. Fine for a trusted lab. Dangerous if zone files are writable by the wrong person, synced from the wrong place, or exposed through admin workflows.

### Evidence to review

- README documents `[lang:py]` embedded Python in zone files
- Fast reference: `README.md` lines 224-260

### Suggested fix

At minimum, make scripted zones opt-in and disabled by default in production mode.

## 5. Keep FunkyDNS outside `egressd`

### Why it matters

Even if you keep using FunkyDNS, the cleanest deployment boundary is still:

- `egressd`: CONNECT chain + supervision
- `funkydns`: DNS stub / DoH resolver

Running them as separate services makes restarts, logs, and blast radius much cleaner.

## 6. Missing certs do not actually disable DoH

### Why it matters

Server mode claims SSL features are disabled when cert files are missing, but
the process still tries to start Hypercorn with those missing PEM paths. That
leaves UDP/TCP DNS up while DoH dies later in startup.

### Suggested fix

When certs are absent and auto-cert is off, either:

- explicitly disable DoH and DoT in config before startup continues, or
- fail fast and exit non-zero before any partial listener set comes up.

Status:
- patched in this vendored copy on 2026-03-17 by disabling DoH and DoT when
  TLS files are missing and `AUTO_CERT` is off, plus a defensive DoH startup
  guard.
- carry the same fix forward on future FunkyDNS rebases.

## 7. Server mode does not stop reliably on container signals

### Why it matters

In the smoke harness, direct `SIGTERM` and `SIGINT` delivery to the
`funkydns server` process does not reliably stop it, which leaves local wrapper
code doing bounded shutdown on its behalf.

### Suggested fix

Rework the server-mode signal path so shutdown is scheduled from the active
event loop in a way that reliably stops the UDP, TCP, and DoH tasks on
`SIGTERM` and `SIGINT`.

## 8. Local host resolution should match the host OS

### Why it matters

Operators expect a local resolver to respect `/etc/hosts` and the system
resolver configuration in `/etc/resolv.conf`, including Ubuntu-style
`systemd-resolved` search domains and stub resolvers.

### Suggested fix

Prefer local resolution in this order:

- `/etc/hosts`
- local zones
- the resolver loaded from `resolv.conf`
- explicit upstream DNS and DoH servers

Status:
- patched in this vendored copy on 2026-03-17
- added config toggles for `USE_SYSTEM_RESOLVER`, `RESOLV_CONF_PATH`,
  `RESPECT_HOSTS_FILE`, and `HOSTS_FILE_PATH`
- added regression tests for hosts-file resolution and `resolv.conf` search
  behavior
- the smoke harness now mounts custom `hosts` and `resolv.conf` fixtures and
  proves both behaviors over direct DNS and DoH
