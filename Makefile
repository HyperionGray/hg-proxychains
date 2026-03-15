.PHONY: smoke down logs health ready bundle pycheck unittest

smoke:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

health:
	curl -fsS http://localhost:9191/health | python3 -m json.tool

ready:
	curl -fsS http://localhost:9191/ready | python3 -m json.tool

pycheck:
	python3 -m py_compile egressd/supervisor.py egressd/chain.py egressd/test_supervisor_readiness.py client/test_client.py exitserver/echo_server.py

unittest:
	python3 -m unittest egressd/test_supervisor_readiness.py

bundle:
	tar -czf egressd-starter.tar.gz .
