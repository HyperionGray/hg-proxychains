.PHONY: smoke down logs health bundle pycheck test check

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

unittest:
	python3 -m unittest egressd/test_supervisor_readiness.py

test:
	python3 -m unittest discover -s egressd -p "test_*.py"

check: pycheck test

test:
	python3 -m unittest egressd/test_supervisor.py

validate-config:
	docker compose run --rm --no-deps --build -e EGRESSD_VALIDATE_ONLY=1 egressd python3 /opt/egressd/supervisor.py

test:
	python3 -m unittest egressd/test_supervisor.py scripts/test_repo_hygiene.py

repo-scan:
	python3 scripts/repo_hygiene.py scan --repo-root .

repo-clean:
	python3 scripts/repo_hygiene.py clean --repo-root .

bundle:
	tar -czf egressd-starter.tar.gz .

clean:
	rm -rf __pycache__ client/__pycache__ egressd/__pycache__ exitserver/__pycache__
	rm -f *.log egressd-starter.tar.gz
