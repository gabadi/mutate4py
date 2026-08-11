"""Unit tests for _sidecar_io.py (dict-shaped JSON sidecar files)."""

import json

from mutate4py._sidecar_io import (
    parse_json_text,
    read_json_sidecar,
    serialize_json_sidecar,
    write_json_sidecar,
)

# ── parse_json_text ───────────────────────────────────────────────────────────


def test_parse_json_text_valid():
    result, ok = parse_json_text('{"a": 1}')
    assert ok is True
    assert result == {"a": 1}


def test_parse_json_text_invalid():
    result, ok = parse_json_text("not-json")
    assert ok is False
    assert result is None


# ── serialize_json_sidecar (pure) ─────────────────────────────────────────────


def test_serialize_json_sidecar_is_pretty_printed():
    text = serialize_json_sidecar({"schema": 1, "functions": [{"id": "func/foo"}]})
    assert "\n" in text.strip()  # indent=2 spreads keys across lines
    assert text.endswith("\n")


def test_serialize_json_sidecar_round_trips_through_parse():
    data = {"schema": 1, "functions": [{"id": "func/foo", "hash": "abc"}]}
    result, ok = parse_json_text(serialize_json_sidecar(data))
    assert ok is True
    assert result == data


# ── read_json_sidecar / write_json_sidecar (file IO) ──────────────────────────


def test_read_json_sidecar_missing_file_returns_none_false(tmp_path):
    assert read_json_sidecar(str(tmp_path / "absent.json")) == (None, False)


def test_read_json_sidecar_invalid_json_returns_none_false(tmp_path):
    p = tmp_path / "sidecar.json"
    p.write_text("{not valid json")

    assert read_json_sidecar(str(p)) == (None, False)


def test_read_json_sidecar_non_dict_json_returns_none_false(tmp_path):
    p = tmp_path / "sidecar.json"
    p.write_text(json.dumps([1, 2, 3]))

    assert read_json_sidecar(str(p)) == (None, False)


def test_write_json_sidecar_round_trips_through_read(tmp_path):
    p = str(tmp_path / "sidecar.json")
    data = {"schema": 1, "functions": []}

    write_json_sidecar(p, data)
    result, ok = read_json_sidecar(p)

    assert ok is True
    assert result == data


def test_write_json_sidecar_overwrites_previous_content(tmp_path):
    p = str(tmp_path / "sidecar.json")

    write_json_sidecar(p, {"schema": 1, "functions": [{"id": "func/old"}]})
    write_json_sidecar(p, {"schema": 1, "functions": [{"id": "func/new"}]})
    result, _ = read_json_sidecar(p)

    assert result["functions"] == [{"id": "func/new"}]
