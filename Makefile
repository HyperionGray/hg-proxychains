COMPOSE ?= podman-compose
PODMAN ?= podman
PYTHON ?= python3
EGRESSD_IMAGE ?= localhost/hg-proxychains-egressd-validate:latest

.PHONY: deps smoke down logs health ready pycheck unittest test check preflight validate-config validate-image repo-scan repo-clean maintenance maintenance-fix bundle clean

deps:
	scripts/bootstrap-third-party.sh

smoke:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f --tail=200

health:
	curl -fsS http://localhost:9191/health | $(PYTHON) -m json.tool

ready:
	curl -i http://localhost:9191/ready

pycheck:
	$(PYTHON) -m py_compile egressd/supervisor.py egressd/chain.py egressd/readiness.py egressd/preflight.py egressd/test_supervisor.py egressd/test_supervisor_readiness.py client/test_client.py exitserver/echo_server.py funkydns-smoke/check_resolution.py funkydns-smoke/generate_cert.py funkydns-smoke/run_funkydns.py

unittest:
	$(PYTHON) -m unittest egressd/test_supervisor_readiness.py egressd/test_supervisor.py tests/test_readiness.py tests/test_supervisor.py scripts/test_repo_hygiene.py

test: unittest

check: pycheck test

validate-image:
	$(PODMAN) build -t $(EGRESSD_IMAGE) ./egressd

preflight: validate-image
	$(PODMAN) run --rm -e EGRESSD_VALIDATE_ONLY=1 -e EGRESSD_PREFLIGHT_SKIP_BIN_CHECKS=1 $(EGRESSD_IMAGE) $(PYTHON) /opt/egressd/supervisor.py --check-config

validate-config: validate-image
	$(PODMAN) run --rm -e EGRESSD_VALIDATE_ONLY=1 $(EGRESSD_IMAGE) $(PYTHON) /opt/egressd/supervisor.py

repo-scan:
	$(PYTHON) scripts/repo_hygiene.py scan --repo-root .

repo-clean:
	$(PYTHON) scripts/repo_hygiene.py clean --repo-root .

maintenance:
	$(PYTHON) scripts/repo_maintenance.py

maintenance-fix:
	$(PYTHON) scripts/repo_maintenance.py --fix

repo-scan-json:
	python3 scripts/repo_hygiene.py scan --repo-root . --json

maintenance:
	python3 scripts/repo_maintenance.py --no-include-third-party

maintenance-fix:
	python3 scripts/repo_maintenance.py --no-include-third-party --fix

maintenance-json:
	python3 scripts/repo_maintenance.py --no-include-third-party --json

maintenance-all:
	python3 scripts/repo_maintenance.py

maintenance-all-json:
	python3 scripts/repo_maintenance.py --json

maintenance:
	python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

maintenance-fix:
	python3 scripts/repo_hygiene.py clean --repo-root . --include-third-party

maintenance-baseline:
	python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party

maintenance:
	python3 scripts/repo_maintenance.py --no-include-third-party

maintenance-fix:
	python3 scripts/repo_maintenance.py --no-include-third-party --fix

bundle:
	tar -czf egressd-starter.tar.gz .

clean:
	rm -rf __pycache__ client/__pycache__ egressd/__pycache__ exitserver/__pycache__ tests/__pycache__ scripts/__pycache__
	rm -f *.log egressd-starter.tar.gz
