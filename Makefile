.PHONY: smoke down logs health ready pycheck unittest test check validate-config repo-scan repo-clean maintenance maintenance-fix bundle clean

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
	python3 -m py_compile egressd/supervisor.py egressd/chain.py egressd/test_supervisor.py egressd/test_supervisor_readiness.py scripts/repo_hygiene.py scripts/repo_maintenance.py client/test_client.py exitserver/echo_server.py

unittest:
	python3 -m unittest discover -s egressd -p "test_*.py"

test:
	python3 -m unittest discover -s egressd -p "test_*.py"
	python3 -m unittest discover -s scripts -p "test_*.py"
	python3 -m unittest discover -s tests -p "test_*.py"

check: pycheck test

validate-config:
	docker compose run --rm --no-deps --build -e EGRESSD_VALIDATE_ONLY=1 egressd python3 /opt/egressd/supervisor.py

repo-scan:
	python3 scripts/repo_maintenance.py --root .

repo-clean:
	python3 scripts/repo_maintenance.py --root . --fix

maintenance: repo-scan

maintenance-fix: repo-clean

bundle:
	tar -czf egressd-starter.tar.gz .

clean:
	rm -rf __pycache__ client/__pycache__ egressd/__pycache__ exitserver/__pycache__ scripts/__pycache__ tests/__pycache__
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -f *.log egressd-starter.tar.gz
