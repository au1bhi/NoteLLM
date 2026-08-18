#! /usr/bin/env bash

set -e
set -x

# Let the DB start
python app/backend_pre_start.py

# Run migrations under the same database advisory lock used by service starts.
python -m app.migration_gate

# Create initial data in DB
python app/initial_data.py
