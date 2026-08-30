# Devcontainer image for Rentora — Python 3.12 + Node 22.
FROM python:3.12-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends git curl \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y nodejs \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /workspaces/rentora