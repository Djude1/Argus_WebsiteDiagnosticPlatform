FROM python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49

ARG SQLMAP_COMMIT=ea8c6bdb63a3b2da1584f328836eb0d28116f7c4
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ADD https://github.com/sqlmapproject/sqlmap/archive/ea8c6bdb63a3b2da1584f328836eb0d28116f7c4.tar.gz /tmp/sqlmap.tar.gz
RUN mkdir -p /opt/sqlmap \
    && tar -xzf /tmp/sqlmap.tar.gz --strip-components=1 -C /opt/sqlmap \
    && rm /tmp/sqlmap.tar.gz \
    && case "$(/usr/local/bin/python /opt/sqlmap/sqlmap.py --version)" in 1.10*) true ;; *) false ;; esac
COPY --chown=65532:65532 runner.py /opt/argus/runner.py
ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/python", "/opt/argus/runner.py"]
