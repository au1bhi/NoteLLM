"""Serialize Alembic upgrades run by container startup paths."""

import subprocess

from sqlalchemy import text

from app.core.db import engine

# Stable project-specific PostgreSQL advisory lock key ("NoteLLM" encoded as
# an integer). Session-scoped locks are released automatically if a container
# is killed while migrating.
_MIGRATION_LOCK_ID = 0x4E6F74654C4C4D


def main() -> None:
    with engine.connect() as connection:
        connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": _MIGRATION_LOCK_ID},
        )
        try:
            subprocess.run(["alembic", "upgrade", "head"], check=True)
            subprocess.run(["alembic", "current", "--check-heads"], check=True)
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": _MIGRATION_LOCK_ID},
            )


if __name__ == "__main__":
    main()
