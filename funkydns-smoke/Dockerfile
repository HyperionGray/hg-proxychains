FROM python:3.11-slim

WORKDIR /opt/funkydns

COPY third_party/FunkyDNS /opt/funkydns/
COPY funkydns-smoke/check_resolution.py /opt/funkydns-smoke/check_resolution.py
COPY funkydns-smoke/generate_cert.py /opt/funkydns-smoke/generate_cert.py
COPY funkydns-smoke/run_funkydns.py /opt/funkydns-smoke/run_funkydns.py
COPY funkydns-smoke/zones /opt/funkydns-smoke/zones
COPY funkydns-smoke/upstream-zones /opt/funkydns-smoke/upstream-zones

RUN pip install --no-cache-dir . aiosqlite \
    && mkdir -p /opt/funkydns-smoke/tls \
    && python3 /opt/funkydns-smoke/generate_cert.py \
        --cert /opt/funkydns-smoke/tls/fullchain.pem \
        --key /opt/funkydns-smoke/tls/privkey.pem \
        --common-name funky \
        --dns-name funky \
        --dns-name localhost \
        --ip-address 127.0.0.1

EXPOSE 53/udp 53/tcp 443
ENV ZONES_DIR=/opt/funkydns-smoke/zones
CMD ["python3", "/opt/funkydns-smoke/run_funkydns.py", "funkydns", "server", "--dns-port", "53", "--doh-port", "443", "--cert-path", "/opt/funkydns-smoke/tls/fullchain.pem", "--key-path", "/opt/funkydns-smoke/tls/privkey.pem", "--no-dot"]
