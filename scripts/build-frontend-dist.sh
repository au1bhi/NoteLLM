#!/usr/bin/env bash
#
# Build the frontend SPA and package it as a deployable artifact, WITHOUT
# touching the server. Use this on a machine with enough RAM (your laptop or
# CI) to produce `frontend-dist.tar.gz`, then either:
#
#   a) push it as a GitHub Release asset named `frontend-dist-<version>.tar.gz`
#      and let install.sh's low-memory mode download it automatically, or
#   b) upload it to the server and point install.sh at it
#      (FRONTEND_DIST_URL, or place it at <repo>/frontend-dist.tar.gz), or
#   c) inject it into the running frontend container directly:
#        docker compose -f compose.yml -f compose.traefik.yml \
#          -f compose.lowmem.yml cp frontend-dist.tar.gz frontend:/tmp/ \
#        && docker compose -f compose.yml -f compose.traefik.yml \
#          -f compose.lowmem.yml exec frontend \
#          sh -c 'tar -xzf /tmp/frontend-dist.tar.gz -C /usr/share/nginx/html && rm /tmp/frontend-dist.tar.gz'
#
# This is the frontend half of the low-memory deployment path: the SPA is
# compiled once here instead of on the (often RAM-starved) server.
set -euo pipefail

cd "$(dirname "$0")/../frontend"

echo "==> Installing dependencies + building SPA ..."
bun install --frozen-lockfile
# CRITICAL: the release artifact MUST target the same origin. A local
# frontend/.env.local (or a locally-added VITE_API_URL) would otherwise bake a
# machine-specific URL into the artifact, making every user's browser send all
# API/auth traffic to a wrong host (app broken + credential-exfiltration
# surface). Empty string = same-origin /api (nginx proxies to the backend),
# matching the in-image build (compose.yml passes VITE_API_URL: "").
VITE_API_URL="" bun run build

OUT="../frontend-dist.tar.gz"
tar -czf "$OUT" -C dist .
echo "OK: built SPA -> $OUT ($(du -h "$OUT" | cut -f1))"
