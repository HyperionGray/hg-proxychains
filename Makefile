PF      ?= ./pf.py
COMPOSE ?= podman-compose
PODMAN  ?= podman
PYTHON  ?= python3
EGRESSD_IMAGE ?= localhost/hg-proxychains-egressd-validate:latest

# pf.py is the canonical entry-point; these targets just delegate so
# operators who type `make` out of habit still get the right behavior.

.PHONY: up down logs run shell status health ready smoke deps bootstrap \
        pycheck unittest test check preflight validate-config validate-image \
        repo-scan repo-scan-json repo-clean \
        maintenance maintenance-json maintenance-fix maintenance-all \
        maintenance-all-json maintenance-baseline bundle clean help

help:
	@$(PF) --help

up:
	$(PF) up --build

down:
	$(PF) down -v

logs:
	$(PF) logs -f --tail 200

shell:
	$(PF) shell

status:
	$(PF) status

health:
	$(PF) health

ready:
	$(PF) ready

smoke:
	$(PF) smoke --build

deps bootstrap:
	$(PF) bootstrap

pycheck:
	$(PF) pycheck

unittest test:
	$(PF) test

check:
	$(PF) check

validate-image:
	$(PODMAN) build -t $(EGRESSD_IMAGE) ./egressd

preflight: validate-image
	$(PODMAN) run --rm -e EGRESSD_VALIDATE_ONLY=1 -e EGRESSD_PREFLIGHT_SKIP_BIN_CHECKS=1 $(EGRESSD_IMAGE) $(PYTHON) /opt/egressd/supervisor.py --check-config

validate-config: validate-image
	$(PODMAN) run --rm -e EGRESSD_VALIDATE_ONLY=1 $(EGRESSD_IMAGE) $(PYTHON) /opt/egressd/supervisor.py

repo-scan:
	$(PYTHON) scripts/repo_hygiene.py scan --repo-root . --no-include-third-party

repo-clean:
	$(PYTHON) scripts/repo_hygiene.py clean --repo-root . --no-include-third-party

repo-scan-json:
	$(PYTHON) scripts/repo_hygiene.py scan --repo-root . --no-include-third-party --json

maintenance:
	$(PYTHON) scripts/repo_maintenance.py --no-include-third-party

maintenance-fix:
	$(PYTHON) scripts/repo_maintenance.py --no-include-third-party --fix

maintenance-json:
	$(PYTHON) scripts/repo_maintenance.py --no-include-third-party --json

maintenance-all:
	$(PYTHON) scripts/repo_maintenance.py --include-third-party

maintenance-all-json:
	$(PYTHON) scripts/repo_maintenance.py --include-third-party --json

maintenance-baseline:
	$(PYTHON) scripts/repo_hygiene.py baseline --repo-root . --include-third-party

bundle:
	tar -czf egressd-starter.tar.gz .

clean:
	rm -rf __pycache__ client/__pycache__ egressd/__pycache__ exitserver/__pycache__ tests/__pycache__ scripts/__pycache__ wrapper/__pycache__
	rm -f *.log egressd-starter.tar.gz
