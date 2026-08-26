#!/usr/bin/env bash

set -e
set -x

coverage run -m pytest tests/
coverage report
coverage html --title "${@-coverage}"

# Blue-team floors: the security ring (SSRF pinning, provider key handling,
# quota reservation, rate limiting, turnstile) must stay essentially fully
# covered. A drop here is a release blocker — these files gate every BYOK
# request the server makes.
coverage report \
    --include="app/core/ssrf.py,app/core/turnstile.py,app/core/security.py,app/services/provider_settings.py" \
    --fail-under=100
coverage report \
    --include="app/core/rate_limit.py,app/services/usage.py" \
    --fail-under=99
