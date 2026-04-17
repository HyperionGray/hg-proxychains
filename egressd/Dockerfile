FROM python:3.11-slim

WORKDIR /opt/egressd

COPY requirements.txt /opt/egressd/
RUN pip install --no-cache-dir -r /opt/egressd/requirements.txt

COPY supervisor.py chain.py readiness.py preflight.py connect_gateway.py config.json5 /opt/egressd/

EXPOSE 15001 9191

CMD ["python3", "/opt/egressd/supervisor.py"]
