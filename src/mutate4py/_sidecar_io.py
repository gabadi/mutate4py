"""Reading and writing dict-shaped JSON sidecar files.

The Manifest keeps its state in a JSON file sitting beside the source file it
describes (`<source>.py.manifest.json`, see `_manifest_storage.py`). This module
is the file format alone and knows no schema, which is why it sits in
`primitives`, where the Manifest layers reach it for free (see tach.toml's
header).
"""

import json
import os

__all__ = ["parse_json_text", "read_json_sidecar", "serialize_json_sidecar", "write_json_sidecar"]


def serialize_json_sidecar(data: dict) -> str:
    """Render data as sidecar-file JSON text: pretty-printed with a trailing newline."""
    return json.dumps(data, indent=2) + "\n"


def parse_json_text(text: str) -> tuple[dict | None, bool]:
    """Parse JSON text. Parse failure => (None, False), never an error."""
    try:
        return json.loads(text), True
    except (json.JSONDecodeError, ValueError):
        return None, False


def read_json_sidecar(path: str) -> tuple[dict | None, bool]:
    """Read and parse path as a JSON sidecar file.

    Missing file, parse failure, or valid-but-non-dict JSON => (None, False),
    never an error: a sidecar is a cache of something derivable, so an
    unusable one is a reason to redo the work, not to fail.
    """
    if not os.path.isfile(path):
        return None, False
    with open(path) as f:
        text = f.read()
    parsed, ok = parse_json_text(text)
    return (parsed, True) if ok and isinstance(parsed, dict) else (None, False)


def write_json_sidecar(path: str, data: dict) -> None:
    """Write data as a JSON sidecar file (pretty-printed, trailing newline)."""
    text = serialize_json_sidecar(data)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp_path, "w") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
