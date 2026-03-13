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
