#!/usr/bin/env bash

set -euo pipefail

# Compose's one-shot prestart service is the primary migration gate. Run the
# idempotent upgrade here as well so direct container restarts, development
# source sync, and scheduler-only restarts cannot run newer code on an older
# schema. An image older than the database fails here with Alembic's explicit
# unknown-revision error instead of starting an API that later returns 503.
python -m app.migration_gate

exec "$@"
