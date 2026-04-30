FROM python:3.11-slim
WORKDIR /opt/client
RUN python3 -m pip install --no-cache-dir dnspython
COPY test_client.py /opt/client/
CMD ["python3", "/opt/client/test_client.py"]
