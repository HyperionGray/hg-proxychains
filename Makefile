COMPOSE ?= podman-compose
PODMAN ?= podman
PYTHON ?= python3
EGRESSD_IMAGE ?= localhost/hg-proxychains-egressd-validate:latest

.PHONY: deps smoke local-smoke down logs health ready pycheck unittest test check preflight validate-config validate-image repo-scan repo-scan-json repo-clean maintenance maintenance-json maintenance-fix maintenance-all maintenance-all-json maintenance-baseline bundle clean

deps:
	scripts/bootstrap-third-party.sh

smoke:
	$(COMPOSE) up --build

local-smoke:
	"/workspace/.venv/bin/python" scripts/local_smoke_test.py

down:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f --tail=200

health:
	curl -fsS http://localhost:9191/health | $(PYTHON) -m json.tool

ready:
	curl -i http://localhost:9191/ready

pycheck:
	$(PYTHON) -m py_compile egressd/connect_gateway.py egressd/supervisor.py egressd/chain.py egressd/readiness.py egressd/preflight.py egressd/test_supervisor.py egressd/test_supervisor_readiness.py client/test_client.py exitserver/echo_server.py funkydns-smoke/check_resolution.py funkydns-smoke/generate_cert.py funkydns-smoke/prepare_resolv_conf.py funkydns-smoke/run_funkydns.py tests/test_chain.py tests/test_preflight.py tests/test_hop_connectivity.py tests/test_host_scripts.py tests/test_compose_config.py scripts/local_smoke_test.py scripts/repo_hygiene.py scripts/repo_maintenance.py scripts/test_repo_hygiene.py

unittest:
	$(PYTHON) -m unittest egressd/test_supervisor_readiness.py egressd/test_supervisor.py tests/test_readiness.py tests/test_supervisor.py tests/test_chain.py tests/test_preflight.py tests/test_hop_connectivity.py tests/test_host_scripts.py tests/test_compose_config.py scripts/test_repo_hygiene.py scripts/test_repo_maintenance.py

test: unittest

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

maintenance:
	$(PYTHON) scripts/repo_maintenance.py --no-include-third-party

maintenance-fix:
	$(PYTHON) scripts/repo_maintenance.py --no-include-third-party --fix

repo-scan-json:
	$(PYTHON) scripts/repo_hygiene.py scan --repo-root . --no-include-third-party --json

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
