import hashlib
import io
import subprocess
import tarfile
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INSTALL_SCRIPT = REPOSITORY_ROOT / "install.sh"


@pytest.fixture(scope="session", autouse=True)
def db() -> None:
    """Keep install-script tests independent from PostgreSQL."""


def _run_function(function: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    command = (
        'script="$1"; shift; function="$1"; shift; arguments=("$@"); '
        'set --; source "$script"; "$function" "${arguments[@]}"'
    )
    return subprocess.run(
        ["bash", "-c", command, "bash", str(INSTALL_SCRIPT), function, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_tar(path: Path, entries: list[tuple[str, bytes, str]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content, entry_type in entries:
            member = tarfile.TarInfo(name)
            if entry_type == "file":
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            elif entry_type == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "/tmp/outside"
                archive.addfile(member)


def test_frontend_archive_requires_safe_root_index(tmp_path: Path) -> None:
    archive = tmp_path / "frontend.tar.gz"
    _write_tar(
        archive,
        [("index.html", b"ok", "file"), ("assets/app.js", b"js", "file")],
    )

    result = _run_function("validate_tar_archive", str(archive), "1024", "1")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "entries",
    [
        [("../outside", b"bad", "file"), ("index.html", b"ok", "file")],
        [("index.html", b"ok", "file"), ("assets/link", b"", "symlink")],
    ],
)
def test_frontend_archive_rejects_escape_and_links(
    tmp_path: Path,
    entries: list[tuple[str, bytes, str]],
) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    _write_tar(archive, entries)

    result = _run_function("validate_tar_archive", str(archive), "1024", "1")

    assert result.returncode != 0


def test_sha256_verification_fails_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"trusted")
    expected = hashlib.sha256(b"trusted").hexdigest()

    assert _run_function("verify_sha256", str(artifact), expected).returncode == 0
    assert _run_function("verify_sha256", str(artifact), "0" * 64).returncode != 0
