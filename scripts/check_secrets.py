"""Fail if a tracked source file contains an obvious hard-coded secret (PRD NFR-08).

Checks git-tracked .py/.toml/.json/.ini/.cfg files for literal passwords, tokens or
private keys. Credentials must come from environment variables (IDLEGRID_*).
"""

import re
import subprocess
import sys

PATTERNS = [
    re.compile(r"""(?i)\b(password|passwd|pwd|secret|api_key|token)\b\s*['"]?\s*[:=]\s*['"][^'"\s]{3,}['"]"""),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]
SUFFIXES = (".py", ".toml", ".json", ".ini", ".cfg")


def main() -> int:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    hits = []
    for path in files:
        if not path.endswith(SUFFIXES) or path.startswith("docs/") or path == "scripts/check_secrets.py":
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(p.search(line) for p in PATTERNS):
                hits.append(f"{path}:{lineno}: {line.strip()[:120]}")
    if hits:
        print("Possible hard-coded secrets (use environment variables instead):")
        print("\n".join(hits))
        return 1
    print(f"No hard-coded secrets found in {len(files)} tracked files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
