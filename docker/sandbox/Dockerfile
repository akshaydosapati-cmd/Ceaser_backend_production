FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip git ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
USER 1000:1000

LABEL org.opencontainers.image.title="CEASER Bolt Sandbox" \
      org.opencontainers.image.description="Unprivileged Node/Python/Git runtime for isolated CEASER cloud coding jobs"
