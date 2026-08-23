"""Repository-local secret and forbidden-file guard."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {
    ".git",
    ".venv",
    ".bootstrap-venv",
    ".tools",
    "__pycache__",
    "data",
    "artifacts",
}
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".env",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
FORBIDDEN_FILENAMES = {".env", "id_rsa", "id_ed25519"}
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "non-empty Upbit key": re.compile(r"(?m)^QF_UPBIT_(?:ACCESS|SECRET)_KEY\s*=\s*[^\s#][^\r\n]*$"),
    "long bearer token": re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]{32,}=*"),
}


def candidate_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not any(part in IGNORED_PARTS for part in path.parts)
        and path.suffix.lower() in TEXT_SUFFIXES
    ]


def main() -> int:
    findings: list[str] = []
    for path in candidate_files():
        relative = path.relative_to(ROOT)
        if path.name in FORBIDDEN_FILENAMES:
            findings.append(f"forbidden file: {relative}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append(f"{label}: {relative}")

    if findings:
        print("Secret scan failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print(f"Secret scan passed ({len(candidate_files())} text files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
