"""Read-only local workspace diagnostics."""

from __future__ import annotations

import importlib.util
import json
import platform
import sqlite3
import sys
from pathlib import Path


def diagnose(workspace: Path = Path.cwd()) -> dict[str, object]:
    required_directories = [
        "data/raw",
        "data/review",
        "data/processed",
        "data/embeddings",
    ]
    return {
        "python": platform.python_version(),
        "python_supported": sys.version_info >= (3, 12),
        "pydantic_available": importlib.util.find_spec("pydantic") is not None,
        "pypdf_available": importlib.util.find_spec("pypdf") is not None,
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_fts5": _has_fts5(),
        "workspace": str(workspace),
        "directories": {name: (workspace / name).is_dir() for name in required_directories},
        "env_present": (workspace / ".env").is_file(),
    }


def _has_fts5() -> bool:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()


def main() -> int:
    report = diagnose()
    print(json.dumps(report, indent=2))
    required = [
        report["python_supported"],
        report["pydantic_available"],
        report["pypdf_available"],
        report["sqlite_fts5"],
    ]
    return 0 if all(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
