#!/usr/bin/env python3
"""Refuse a PyPI publish that is not running from the matching release tag.

The publish workflow builds whatever ref it is dispatched from, and the
GitHub UI defaults that to `main`, which carries a `.devN` version between
releases. Dispatched from `main` while cutting 0.10.0, it uploaded
0.10.1.dev0 to PyPI instead (issue #559). PyPI never accepts the same
version twice, so this check runs before anything is built or uploaded.

Usage (from the publish workflow):

    python scripts/check_release_ref.py --target pypi

Reads `GITHUB_REF_TYPE` and `GITHUB_REF_NAME` from the environment, and the
version from `src/canarchy/__init__.py`, the file hatch builds the package
version from. Exits 0 when publishing may proceed and 1 with the reasons
otherwise. Targets other than `pypi` are not restricted: TestPyPI is the
runbook's sandbox for rehearsing workflow changes.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parents[1] / "src" / "canarchy" / "__init__.py"

# A final release is exactly X.Y.Z. Anything else -- `.devN`, `rcN`, `aN`,
# `bN`, `.postN`, a `+local` segment -- must never reach PyPI from here.
FINAL_RELEASE = re.compile(r"\d+\.\d+\.\d+")

RESTRICTED_TARGETS = frozenset({"pypi"})


def read_version(path: Path | None = None) -> str:
    """Return the `__version__` string assigned in `path` (default: the package)."""
    path = VERSION_FILE if path is None else path
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', text, re.MULTILINE)
    if match is None:
        raise ValueError(f"no __version__ assignment found in {path}")
    return match.group(1)


def check(target: str, ref_type: str, ref_name: str, version: str) -> list[str]:
    """Return the reasons publishing must not proceed; empty means it may."""
    if target not in RESTRICTED_TARGETS:
        return []

    problems: list[str] = []
    if ref_type != "tag":
        problems.append(
            f"dispatched from {ref_type or 'an unknown ref type'} '{ref_name}', not a tag; "
            f"publishing to {target} must run from the release tag -- select it under "
            "'Use workflow from' > Tags, not a branch"
        )
    if not FINAL_RELEASE.fullmatch(version):
        problems.append(
            f"package version '{version}' is not a final release (X.Y.Z); development, "
            f"pre-release and local versions must not be published to {target}"
        )
    elif ref_type == "tag" and ref_name != f"v{version}":
        problems.append(
            f"tag '{ref_name}' does not match the package version; expected 'v{version}'"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True, help="publication target, e.g. pypi")
    args = parser.parse_args(argv)

    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    version = read_version()

    problems = check(args.target, ref_type, ref_name, version)
    for problem in problems:
        # `::error::` surfaces as an annotation on the workflow run summary.
        print(f"::error::{problem}")
    if problems:
        return 1

    if args.target in RESTRICTED_TARGETS:
        print(f"release ref OK: tag '{ref_name}' matches final version {version}")
    else:
        print(f"target '{args.target}' is not restricted; skipping release ref check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
