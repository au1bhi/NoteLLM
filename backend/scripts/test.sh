#!/usr/bin/env bash

set -e

# Prefer an already-activated environment; fall back to uv.
cov() {
    if command -v coverage >/dev/null 2>&1; then
        "${@}"
    else
        uv run "${@}"
    fi
}

cov coverage run -m pytest tests/
cov coverage report
cov coverage html --title "${1-coverage}"

# Blue-team floors: the security ring (SSRF pinning, provider key handling,
# quota reservation, rate limiting, turnstile) must stay essentially fully
# covered. A drop here is a release blocker — these files gate every BYOK
# request the server makes.
cov coverage report \
    --include="app/core/ssrf.py,app/core/turnstile.py,app/core/security.py,app/services/provider_settings.py" \
    --fail-under=100
cov coverage report \
    --include="app/core/rate_limit.py,app/services/usage.py" \
    --fail-under=99
