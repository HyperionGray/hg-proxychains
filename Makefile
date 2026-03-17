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

bundle:
	tar -czf egressd-starter.tar.gz .

clean:
	rm -rf __pycache__ client/__pycache__ egressd/__pycache__ exitserver/__pycache__
	rm -f *.log egressd-starter.tar.gz
