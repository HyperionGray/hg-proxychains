.PHONY: smoke down logs health ready pycheck unittest test check validate-config repo-scan repo-clean repo-scan-json maintenance maintenance-fix maintenance-json maintenance-all maintenance-all-json bundle clean

smoke:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

health:
	curl -fsS http://localhost:9191/health | python3 -m json.tool

ready:
	curl -i http://localhost:9191/ready

pycheck:
	python3 -m py_compile egressd/supervisor.py egressd/chain.py egressd/test_supervisor_readiness.py client/test_client.py exitserver/echo_server.py

test:
	python3 -m unittest tests/test_readiness.py scripts/test_repo_hygiene.py

unittest: test

check: pycheck test

validate-config:
	docker compose run --rm --no-deps --build -e EGRESSD_VALIDATE_ONLY=1 egressd python3 /opt/egressd/supervisor.py

repo-scan:
	python3 scripts/repo_hygiene.py scan --repo-root .

repo-clean:
	python3 scripts/repo_hygiene.py clean --repo-root .

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

bundle:
	tar -czf egressd-starter.tar.gz .

clean:
	rm -rf __pycache__ client/__pycache__ egressd/__pycache__ exitserver/__pycache__
	rm -f *.log egressd-starter.tar.gz
