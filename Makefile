.PHONY: smoke down logs health bundle pycheck preflight

smoke:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

health:
	curl -fsS http://localhost:9191/health | python3 -m json.tool

pycheck:
	python3 -m py_compile egressd/supervisor.py egressd/preflight.py egressd/chain.py client/test_client.py exitserver/echo_server.py

preflight:
	python3 egressd/supervisor.py --check-config --config egressd/config.json5

bundle:
	tar -czf egressd-starter.tar.gz .
