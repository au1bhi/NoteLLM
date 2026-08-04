#! /usr/bin/env bash

set -e
set -x

cd backend
uv run python -c "import app.main; import json; print(json.dumps(app.main.app.openapi()))" > ../openapi.json
cd ..
mv openapi.json frontend/
bun run --filter frontend generate-client
# The generator emits whitespace-only indentation on a few blank lines. Keep
# generated output deterministic and friendly to git diff/pre-commit checks.
sed -i 's/[[:space:]]\+$//' frontend/src/client/*.ts
bun run lint
