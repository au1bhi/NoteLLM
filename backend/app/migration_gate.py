"""Serialize Alembic upgrades run by container startup paths."""

import subprocess
import sys

from sqlalchemy import text

from app.core.db import engine

# Stable project-specific PostgreSQL advisory lock key ("NoteMigr" encoded as
# an integer). Keep this distinct from request-path locks so a long migration
# cannot stall rate-limit bucket admission in workers serving the old release.
# Session-scoped locks are released automatically if a container is killed.
_MIGRATION_LOCK_ID = 0x4E6F74654D696772


def main() -> None:
    with engine.connect() as connection:
        connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": _MIGRATION_LOCK_ID},
        )
        try:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"], check=True
            )
            subprocess.run(
                [sys.executable, "-m", "alembic", "current", "--check-heads"],
                check=True,
            )
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": _MIGRATION_LOCK_ID},
            )


if __name__ == "__main__":
    main()
