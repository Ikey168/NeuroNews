#!/usr/bin/env python3
"""
CI gate: fail if any banned cloud env-var prefix appears in src/ or scripts/.

Run:
    python3 scripts/check_cloud_refs.py

Exit 0 → clean.  Exit 1 → violations found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BANNED_PATTERNS: list[str] = [
    "SNOWFLAKE_",
    "REDSHIFT_",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "S3_BUCKET",
    "KAFKA_",
]

SCAN_DIRS: list[Path] = [
    REPO_ROOT / "src",
    REPO_ROOT / "scripts",
]

# Files that are deliberately excluded (archived / vendor / migrations).
EXCLUDE_PREFIXES: list[str] = [
    str(REPO_ROOT / "archive"),
]

_PATTERN = re.compile("|".join(re.escape(p) for p in BANNED_PATTERNS))


def scan() -> list[tuple[Path, int, str]]:
    violations: list[tuple[Path, int, str]] = []
    for scan_dir in SCAN_DIRS:
        for py_file in sorted(scan_dir.rglob("*.py")):
            # Skip the check script itself and archived files
            if py_file == Path(__file__):
                continue
            if any(str(py_file).startswith(ex) for ex in EXCLUDE_PREFIXES):
                continue
            if "__pycache__" in py_file.parts:
                continue
            try:
                for lineno, line in enumerate(py_file.read_text(errors="replace").splitlines(), 1):
                    if _PATTERN.search(line):
                        violations.append((py_file, lineno, line.rstrip()))
            except OSError:
                pass
    return violations


def main() -> int:
    violations = scan()
    if not violations:
        print("check_cloud_refs: OK — no banned cloud env-var references found.")
        return 0

    print(f"check_cloud_refs: FAIL — {len(violations)} violation(s) found:\n")
    for path, lineno, line in violations:
        rel = path.relative_to(REPO_ROOT)
        print(f"  {rel}:{lineno}  {line.strip()}")
    print(f"\nBanned prefixes: {', '.join(BANNED_PATTERNS)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
