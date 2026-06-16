#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("/private/tmp/dialectical-engine-source.tgz")
DEFAULT_REPORT = Path("/private/tmp/dialectical-engine-source-snapshot.json")
EXCLUDE_PATTERNS = [
    ".DS_Store",
    "*/.DS_Store",
    ".git",
    ".git/*",
    ".dialectical-dev",
    ".dialectical-dev/*",
    ".pytest_cache",
    ".pytest_cache/*",
    "*/.pytest_cache",
    "*/.pytest_cache/*",
    ".pycache",
    ".pycache/*",
    "*/.pycache",
    "*/.pycache/*",
    ".venv",
    ".venv/*",
    ".venv*",
    ".venv*/*",
    "__pycache__",
    "__pycache__/*",
    "*/__pycache__",
    "*/__pycache__/*",
    "*.pyc",
    ".coverage",
    "coordinator/.coverage",
    "coordinator/.pytest_cache",
    "coordinator/.pytest_cache/*",
    "worker/.coverage",
    "worker/.pytest_cache",
    "worker/.pytest_cache/*",
    "web/.next",
    "web/.next/*",
    "web/.next-dev*",
    "web/.next-dev*/*",
    "web/node_modules",
    "web/node_modules/*",
    "web/out",
    "web/out/*",
]


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def excluded(relative_path: str) -> bool:
    return any(fnmatch.fnmatch(relative_path, pattern) for pattern in EXCLUDE_PATTERNS)


def source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        relative_path = rel(path, root)
        if excluded(relative_path):
            if path.is_dir():
                continue
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_hash(path: Path) -> str:
    return sha256(path)


def write_archive(root: Path, output: Path, files: list[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=f"dialectical-engine/{rel(path, root)}")


def build_report(root: Path, output: Path, files: list[Path]) -> dict[str, Any]:
    file_entries = [
        {
            "path": rel(path, root),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in files
    ]
    return {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "archive": str(output),
        "archive_sha256": archive_hash(output),
        "file_count": len(file_entries),
        "total_bytes": sum(entry["size"] for entry in file_entries),
        "exclude_patterns": EXCLUDE_PATTERNS,
        "files": file_entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a clean source archive for this local dialectical-engine tree.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output.resolve()
    report_path = args.report_path.resolve()
    files = source_files(root)
    write_archive(root, output, files)
    report = build_report(root, output, files)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Archive: {output}")
    print(f"Report: {report_path}")
    print(f"Files: {report['file_count']}")
    print(f"SHA256: {report['archive_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
