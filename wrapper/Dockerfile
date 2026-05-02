FROM python:3.11-slim

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        proxychains4 \
        ca-certificates \
        curl \
        iputils-ping \
        dnsutils \
        netcat-openbsd \
        less \
    ; \
    rm -rf /var/lib/apt/lists/*

COPY proxychains4.conf /etc/proxychains4.conf
COPY entrypoint.sh /usr/local/bin/hg-pc-entrypoint
RUN chmod +x /usr/local/bin/hg-pc-entrypoint

ENV HTTP_PROXY=http://egressd:15001 \
    HTTPS_PROXY=http://egressd:15001 \
    http_proxy=http://egressd:15001 \
    https_proxy=http://egressd:15001 \
    NO_PROXY=egressd,localhost,127.0.0.1 \
    no_proxy=egressd,localhost,127.0.0.1

WORKDIR /work

ENTRYPOINT ["hg-pc-entrypoint"]
CMD ["sleep", "infinity"]
