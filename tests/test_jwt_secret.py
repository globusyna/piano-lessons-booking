import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_SECRET = "z" * 32


def run_import(module: str, tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    """Import a backend module in a fresh interpreter so the startup guard runs again.

    The guard runs once, at import time, and Python caches modules - so a second in-process
    import would not re-run it. A subprocess is the only way to exercise more than one branch
    within a single test run. PIANO_DATABASE_URL is always pointed at a throwaway file so no
    subprocess can reach the developer's piano.db.
    """
    environment = dict(os.environ)
    environment.pop("PIANO_JWT_SECRET", None)
    environment.pop("PIANO_DEV_MODE", None)
    environment["PIANO_DATABASE_URL"] = f"sqlite+pysqlite:///{tmp_path / 'subprocess.db'}"
    environment.update(overrides)
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=environment,
    )


def test_backend_refuses_to_start_when_no_secret_is_configured(tmp_path: Path) -> None:
    result = run_import("backend.auth", tmp_path)

    assert result.returncode != 0
    assert "PIANO_JWT_SECRET" in result.stderr
    assert "PIANO_DEV_MODE=1" in result.stderr


def test_the_refusal_names_both_ways_to_proceed(tmp_path: Path) -> None:
    result = run_import("backend.auth", tmp_path)

    assert "is not set" in result.stderr
    assert "Set PIANO_JWT_SECRET to a private secret" in result.stderr
    assert "For local development only, set PIANO_DEV_MODE=1" in result.stderr


def test_backend_refuses_to_start_when_the_secret_is_empty(tmp_path: Path) -> None:
    result = run_import("backend.auth", tmp_path, PIANO_JWT_SECRET="")

    assert result.returncode != 0
    assert "PIANO_JWT_SECRET is set but blank" in result.stderr


def test_backend_refuses_to_start_when_the_secret_is_whitespace_only(tmp_path: Path) -> None:
    result = run_import("backend.auth", tmp_path, PIANO_JWT_SECRET="      \t  ")

    assert result.returncode != 0
    assert "PIANO_JWT_SECRET is set but blank" in result.stderr


def test_backend_refuses_to_start_when_the_secret_is_shorter_than_32_characters(
    tmp_path: Path,
) -> None:
    result = run_import("backend.auth", tmp_path, PIANO_JWT_SECRET="z" * 31)

    assert result.returncode != 0
    assert "31 characters long" in result.stderr
    assert "32-character minimum" in result.stderr


def test_the_length_failure_says_the_minimum_is_not_an_entropy_guarantee(tmp_path: Path) -> None:
    result = run_import("backend.auth", tmp_path, PIANO_JWT_SECRET="placeholder")

    assert "not a guarantee of entropy" in result.stderr


def test_a_secret_of_exactly_32_characters_is_accepted(tmp_path: Path) -> None:
    result = run_import("backend.auth", tmp_path, PIANO_JWT_SECRET=VALID_SECRET)

    assert result.returncode == 0
    assert result.stderr == ""


def test_dev_mode_starts_the_backend_without_a_configured_secret(tmp_path: Path) -> None:
    result = run_import("backend.auth", tmp_path, PIANO_DEV_MODE="1")

    assert result.returncode == 0
    assert "generated a development PIANO_JWT_SECRET" in result.stderr
    assert "stop working after the next restart" in result.stderr


def test_dev_mode_generates_a_different_secret_for_every_process(tmp_path: Path) -> None:
    first = read_resolved_secret(tmp_path, "first", PIANO_DEV_MODE="1")
    second = read_resolved_secret(tmp_path, "second", PIANO_DEV_MODE="1")

    assert len(first) >= 32
    assert first != second


def test_dev_mode_never_prints_the_generated_secret(tmp_path: Path) -> None:
    secret_file = tmp_path / "leak-check.txt"
    result = run_secret_probe(tmp_path, secret_file, PIANO_DEV_MODE="1")
    generated = secret_file.read_text()

    assert result.returncode == 0
    assert generated not in result.stderr
    assert generated not in result.stdout


def test_an_explicitly_configured_secret_wins_over_dev_mode(tmp_path: Path) -> None:
    resolved = read_resolved_secret(
        tmp_path, "explicit", PIANO_JWT_SECRET=VALID_SECRET, PIANO_DEV_MODE="1"
    )

    assert resolved == VALID_SECRET


def test_the_guard_fires_before_the_api_and_the_store_are_built(tmp_path: Path) -> None:
    database = tmp_path / "subprocess.db"
    result = run_import("backend.main", tmp_path)

    assert result.returncode != 0
    assert "PIANO_JWT_SECRET" in result.stderr
    assert not database.exists()


def run_secret_probe(
    tmp_path: Path, secret_file: Path, **overrides: str
) -> subprocess.CompletedProcess[str]:
    """Import backend.auth in a fresh interpreter and write the resolved secret to a file.

    The secret goes to a file rather than to stdout so that the captured streams can be checked
    for leaks of the generated value.
    """
    environment = dict(os.environ)
    environment.pop("PIANO_JWT_SECRET", None)
    environment.pop("PIANO_DEV_MODE", None)
    environment["PIANO_DATABASE_URL"] = f"sqlite+pysqlite:///{tmp_path / 'subprocess.db'}"
    environment["PIANO_SECRET_PROBE_FILE"] = str(secret_file)
    environment.update(overrides)
    program = (
        "import os, pathlib, backend.auth;"
        "pathlib.Path(os.environ['PIANO_SECRET_PROBE_FILE'])"
        ".write_text(backend.auth.JWT_SECRET)"
    )
    return subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=environment,
    )


def read_resolved_secret(tmp_path: Path, name: str, **overrides: str) -> str:
    secret_file = tmp_path / f"{name}.txt"
    result = run_secret_probe(tmp_path, secret_file, **overrides)
    assert result.returncode == 0, result.stderr
    return secret_file.read_text()
