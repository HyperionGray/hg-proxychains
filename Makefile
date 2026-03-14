.PHONY: smoke down logs health bundle pycheck preflight
PYTHON := $(if $(wildcard .venv/bin/python3),.venv/bin/python3,python3)

smoke:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

health:
	curl -fsS http://localhost:9191/health | python3 -m json.tool

pycheck:
	$(PYTHON) -m py_compile egressd/supervisor.py egressd/preflight.py egressd/chain.py client/test_client.py exitserver/echo_server.py

preflight:
	EGRESSD_PREFLIGHT_SKIP_BIN_CHECKS=true $(PYTHON) egressd/supervisor.py --check-config --config egressd/config.json5

bundle:
	tar -czf egressd-starter.tar.gz .
