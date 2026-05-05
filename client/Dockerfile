FROM python:3.11-slim
WORKDIR /opt/client
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl iproute2 iptables procps \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip install --no-cache-dir dnspython
COPY runner.py test_client.py hg_proxychains.py /opt/client/
RUN ln -s /opt/client/hg_proxychains.py /usr/local/bin/hg-proxychains
ENTRYPOINT ["python3", "/opt/client/runner.py"]
CMD ["serve"]
