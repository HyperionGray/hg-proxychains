SHELL    := /usr/bin/env bash
WRAPPER  ?= ./hg-proxychains
COMPOSE  ?= podman-compose
PODMAN   ?= podman
PYTHON   ?= python3
EGRESSD_IMAGE ?= localhost/hg-proxychains-egressd-validate:latest

# `./hg-proxychains` is the canonical entry-point; these targets just
# delegate so operators who type `make` out of habit get the right
# behavior. Anything not exposed by the wrapper (preflight, repo
# hygiene) still lives here.

.PHONY: up down logs run shell status smoke deps bootstrap \
        pycheck unittest test check preflight validate-config validate-image \
        repo-scan repo-scan-json repo-clean \
        maintenance maintenance-json maintenance-fix maintenance-all \
        maintenance-all-json maintenance-baseline bundle clean help

help:
	@$(WRAPPER) --help

up:
	$(WRAPPER) up

down:
	$(WRAPPER) down

logs:
	$(WRAPPER) logs

shell:
	$(WRAPPER) shell

status:
	$(WRAPPER) status

run:
	@if [ -z "$(CMD)" ]; then echo 'usage: make run CMD="curl -fsS https://example.com/"' >&2; exit 2; fi
	$(WRAPPER) run -- $(CMD)

smoke:
	$(WRAPPER) smoke

deps bootstrap:
	scripts/bootstrap-third-party.sh

pycheck:
	$(PYTHON) -m py_compile \
	    egressd/supervisor.py egressd/chain.py egressd/readiness.py \
	    egressd/preflight.py egressd/supervisor_hops.py egressd/supervisor_readiness.py \
	    client/runner.py client/hg_proxychains.py client/test_client.py \
	    exitserver/echo_server.py \
	    funkydns-smoke/check_resolution.py funkydns-smoke/generate_cert.py funkydns-smoke/run_funkydns.py \
	    scripts/repo_hygiene.py scripts/repo_maintenance.py scripts/repo_hygiene_lib.py

unittest test:
	$(PYTHON) -m unittest \
	    egressd.test_supervisor_readiness egressd.test_supervisor \
	    tests.test_readiness tests.test_supervisor tests.test_chain \
	    tests.test_preflight tests.test_hop_connectivity \
	    tests.test_client_dockerfile tests.test_egressd_dockerfile \
	    tests.test_proxy_workflow_containers tests.test_exitserver \
	    tests.test_compose_layout tests.test_wrapper_cli \
	    tests.test_client_wrapper tests.test_bootstrap_third_party
	cd scripts && $(PYTHON) -m unittest test_repo_hygiene test_repo_maintenance

check: pycheck test

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
	rm -rf __pycache__ client/__pycache__ egressd/__pycache__ exitserver/__pycache__ tests/__pycache__ scripts/__pycache__
	rm -f *.log egressd-starter.tar.gz
