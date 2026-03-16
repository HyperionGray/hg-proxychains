.PHONY: smoke down logs health bundle pycheck test validate-config

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
	python3 -m unittest egressd/test_supervisor.py

validate-config:
	EGRESSD_CONFIG=egressd/config.json5 EGRESSD_VALIDATE_ONLY=1 python3 egressd/supervisor.py

bundle:
	tar -czf egressd-starter.tar.gz .
