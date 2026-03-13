FROM python:3.11-slim

WORKDIR /opt/funkydns

COPY third_party/FunkyDNS /opt/funkydns/
RUN pip install --no-cache-dir .

EXPOSE 53/udp 53/tcp 443
CMD ["funkydns", "server", "--dns-port", "53", "--doh-port", "443", "--upstream", "https://cloudflare-dns.com/dns-query"]
