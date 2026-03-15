.PHONY: smoke down logs health ready bundle pycheck test clean

smoke:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

health:
	curl -fsS http://localhost:9191/health | python3 -m json.tool

ready:
	curl -fsS -o /tmp/egressd-ready.json -w "%{http_code}\n" http://localhost:9191/ready
	python3 -m json.tool /tmp/egressd-ready.json

pycheck:
	python3 -m py_compile egressd/supervisor.py egressd/chain.py egressd/readiness.py client/test_client.py exitserver/echo_server.py tests/test_readiness.py

test:
	python3 -m unittest discover -s tests -p "test_*.py"

bundle:
	tar -czf egressd-starter.tar.gz .

clean:
	python3 -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__') if p.is_dir()]; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('.pytest_cache') if p.is_dir()]; pathlib.Path('egressd-starter.tar.gz').unlink(missing_ok=True)"
