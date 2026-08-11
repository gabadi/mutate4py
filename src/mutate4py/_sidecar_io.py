"""Reading and writing dict-shaped JSON sidecar files.

Two unrelated things in this project keep state in a JSON file sitting beside
the file it describes: the Manifest (`<source>.py.manifest.json`, see
`_manifest_storage.py`) and the --build-test-contexts staleness cache
(`<db>.test-context-cache.json`, see `_test_context_cache.py`). This module is
the file format alone and knows neither schema, which is why it sits in
`primitives` — both domains reach it for free, with no dependency edge between
them (see tach.toml's header).
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
    with open(path, "w") as f:
        f.write(serialize_json_sidecar(data))
