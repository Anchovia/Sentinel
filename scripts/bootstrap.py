"""Validate the minimum developer toolchain without changing global state."""

from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> int:
    uv = shutil.which("uv")
    if uv is None:
        print("uv was not found. Install it from https://docs.astral.sh/uv/", file=sys.stderr)
        return 1
    completed = subprocess.run([uv, "sync", "--all-groups"], check=False)  # noqa: S603
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
