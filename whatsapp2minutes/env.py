"""
Author: Dr. Denys Dutykh (Khalifa University of Science and Technology, Abu Dhabi, UAE)
"""

import os


def _strip_inline_comment(line: str) -> str:
    """Strip unquoted, unescaped trailing comments beginning with '#'.

    - Preserves '#' inside single or double quotes.
    - Preserves escaped hashes (\\#).
    - Trims trailing whitespace after removing the comment.
    """
    out: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    for ch in line:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            out.append(ch)
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            continue
        if ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _parse_env_file(path: str) -> dict:
    data: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                # Strip unquoted inline comments but preserve '#' in quotes or escaped
                line = _strip_inline_comment(line)
                if not line or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                # Remove optional surrounding quotes
                if val and ((val[0] == val[-1]) and val[0] in {'"', "'"}):
                    val = val[1:-1]
                data[key] = val
    except FileNotFoundError:
        pass
    return data


def load_env(override: bool = False) -> None:
    """Load variables from .env.local and .env into os.environ.

    Precedence:
    - existing os.environ (unless override=True)
    - .env.local
    - .env
    """
    merged: dict[str, str] = {}
    for p in (".env",):
        merged.update(_parse_env_file(p))
    # local overrides last
    merged.update(_parse_env_file(".env.local"))

    for k, v in merged.items():
        if override or (k not in os.environ):
            os.environ[k] = v


def get_env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)
