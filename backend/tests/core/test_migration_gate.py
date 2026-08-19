import subprocess
import sys
from unittest.mock import MagicMock

import pytest
from pytest import MonkeyPatch

from app import migration_gate
from app.core import rate_limit


def test_migration_gate_serializes_upgrade_and_checks_head(
    monkeypatch: MonkeyPatch,
) -> None:
    connection = MagicMock()
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    runs: list[tuple[list[str], bool]] = []

    def record_run(command: list[str], *, check: bool) -> None:
        runs.append((command, check))

    monkeypatch.setattr(migration_gate, "engine", engine)
    monkeypatch.setattr(subprocess, "run", record_run)

    migration_gate.main()

    assert runs == [
        ([sys.executable, "-m", "alembic", "upgrade", "head"], True),
        ([sys.executable, "-m", "alembic", "current", "--check-heads"], True),
    ]
    calls = connection.execute.call_args_list
    assert [call.args[0].text for call in calls] == [
        "SELECT pg_advisory_lock(:lock_id)",
        "SELECT pg_advisory_unlock(:lock_id)",
    ]
    assert [call.args[1] for call in calls] == [
        {"lock_id": migration_gate._MIGRATION_LOCK_ID},
        {"lock_id": migration_gate._MIGRATION_LOCK_ID},
    ]
    assert migration_gate._MIGRATION_LOCK_ID != rate_limit._ADMISSION_LOCK_ID


def test_migration_gate_unlocks_when_upgrade_fails(monkeypatch: MonkeyPatch) -> None:
    connection = MagicMock()
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection

    monkeypatch.setattr(migration_gate, "engine", engine)
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.CalledProcessError(1, "alembic")),
    )

    with pytest.raises(subprocess.CalledProcessError):
        migration_gate.main()

    calls = connection.execute.call_args_list
    assert [call.args[0].text for call in calls] == [
        "SELECT pg_advisory_lock(:lock_id)",
        "SELECT pg_advisory_unlock(:lock_id)",
    ]
