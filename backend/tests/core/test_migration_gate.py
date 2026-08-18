import subprocess
from unittest.mock import MagicMock

from pytest import MonkeyPatch

from app import migration_gate


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
        (["alembic", "upgrade", "head"], True),
        (["alembic", "current", "--check-heads"], True),
    ]
    assert connection.execute.call_count == 2
