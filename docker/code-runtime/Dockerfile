FROM node:22-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
    && corepack --version \
    && npm install -g pnpm@11.2.2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
