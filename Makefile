.PHONY: smoke down logs health bundle pycheck test repo-scan repo-clean

smoke:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

health:
	curl -fsS http://localhost:9191/health | python3 -m json.tool

pycheck:
	python3 -m py_compile egressd/supervisor.py egressd/chain.py client/test_client.py exitserver/echo_server.py

test:
	python3 -m unittest egressd/test_supervisor.py scripts/test_repo_hygiene.py

repo-scan:
	python3 scripts/repo_hygiene.py scan --repo-root .

repo-clean:
	python3 scripts/repo_hygiene.py clean --repo-root .

bundle:
	tar -czf egressd-starter.tar.gz .
