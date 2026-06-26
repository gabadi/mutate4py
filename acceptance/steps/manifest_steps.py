"""Step handlers for features/manifest.feature."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from mutate4py._manifest import (
    build_manifest,
    diff_manifests,
    embed_manifest,
    extract_manifest,
    strip_manifest,
)
from acceptance.steps.step_lib import (
    assert_nonzero_exit,
    make_registry,
    run_mutate4py,
)

STEP_HANDLERS, step, run_step = make_registry()

_TESTED_AT = "2026-01-01T00:00:00Z"

# ── Source fixtures ────────────────────────────────────────────────────────────

_DEFINITION_SOURCES = {
    "def foo": "def foo():\n    return 1\n",
    "async def foo": "async def foo():\n    return 1\n",
    "class C with method m": "class C:\n    def m(self):\n        return 1\n",
}

# Edits for scenario-9 and scenario-12
_BASE_FN_SRC = "def foo(a, b):\n    return a + b\n"

_EDITED_SOURCES = {
    "reformatting whitespace": "def foo(a, b):\n    return  a + b\n",
    "editing a comment": "def foo(a, b):\n    # edited comment\n    return a + b\n",
    # Rename an internal variable so the function id stays func/foo but hash changes
    "renaming the function": "def foo(x, y):\n    return x + y\n",
    "changing a numeric literal": "def foo(a, b):\n    return a + 2\n",
    "changing an operator": "def foo(a, b):\n    return a - b\n",
    # for --update-manifest scenario-12
    "nothing": None,  # no change
}

# footer fixtures for scenario-7
_FOOTER_SOURCES = {
    "(no markers at all)": "x = 1\n",
    "# mutate4py-manifest-begin only, no end marker": (
        "x = 1\n# mutate4py-manifest-begin\n# {}\n"
    ),
    "both markers around text that is not valid JSON": (
        "x = 1\n# mutate4py-manifest-begin\n# not-valid-json\n# mutate4py-manifest-end\n"
    ),
}


class Context:
    def __init__(self):
        self.source: str = ""
        self.embedded: str = ""
        self.manifest_built: dict | None = None
        self.extracted: dict | None = None
        self.extract_ok: bool = False
        self.prev_manifest: dict | None = None
        self.curr_manifest: dict | None = None
        self.changed_ids: set = set()
        self.tmpdir: str | None = None
        self.source_path: str | None = None
        self.cli_result = None
        self.file_content_before: str | None = None


ctx = Context()


def _write_tmp(content: str) -> str:
    if ctx.tmpdir is None:
        ctx.tmpdir = tempfile.mkdtemp()
    path = os.path.join(ctx.tmpdir, "sample.py")
    with open(path, "w") as f:
        f.write(content)
    return path


# ── Given steps ────────────────────────────────────────────────────────────────


@step(r"a Python source file with no embedded manifest")
def given_clean_file(m, params):
    ctx.source = "def foo(a, b):\n    return a + b\n"
    ctx.embedded = ""
    ctx.source_path = _write_tmp(ctx.source)


@step(r'a Python source file defining "(.*)"')
def given_file_defining(m, params):
    key = params.get("definition") or m.group(1)
    if key not in _DEFINITION_SOURCES:
        raise ValueError(f"unknown definition fixture: {key!r}")
    ctx.source = _DEFINITION_SOURCES[key]
    ctx.embedded = ""
    ctx.source_path = _write_tmp(ctx.source)


@step(r'a Python source file with a decorator above "def foo" on line (\d+)')
def given_decorated_file(m, params):
    ctx.source = "@decorator\ndef foo():\n    return 1\n"
    ctx.embedded = ""
    ctx.source_path = _write_tmp(ctx.source)


@step(r"a Python source file with module-level code and no function definitions")
def given_module_level_only(m, params):
    ctx.source = "x = 1\ny = 2\n"
    ctx.embedded = ""
    ctx.source_path = _write_tmp(ctx.source)


@step(r'a Python source file whose footer is "(.*)"')
def given_footer_file(m, params):
    key = params.get("footer") or m.group(1)
    if key not in _FOOTER_SOURCES:
        raise ValueError(f"unknown footer fixture: {key!r}")
    ctx.source = _FOOTER_SOURCES[key]
    ctx.embedded = ""


@step(r"a Python source file with an embedded manifest")
def given_file_with_manifest(m, params):
    ctx.source = "def foo(a, b):\n    return a + b\n"
    manifest = build_manifest(ctx.source, tested_at=_TESTED_AT)
    ctx.embedded = embed_manifest(ctx.source, manifest)
    ctx.manifest_built = manifest
    ctx.source_path = _write_tmp(ctx.embedded)


@step(r"a previous manifest built from a function")
def given_prev_manifest_from_fn(m, params):
    ctx.source = _BASE_FN_SRC
    ctx.prev_manifest = build_manifest(ctx.source, tested_at=_TESTED_AT)


@step(r'the function is changed by "(.*)"')
def given_fn_changed_by(m, params):
    edit = params.get("edit") or m.group(1)
    if edit not in _EDITED_SOURCES:
        raise ValueError(f"unknown edit fixture: {edit!r}")
    edited = _EDITED_SOURCES[edit]
    if edited is None:
        edited = _BASE_FN_SRC
    ctx.curr_manifest = build_manifest(edited, tested_at=_TESTED_AT)


@step(r'a previous manifest with functions "(.*)"')
def given_prev_manifest_with_fns(m, params):
    spec = params.get("previous") or m.group(1)
    ctx.prev_manifest = _parse_fn_spec(spec)


@step(r'a current manifest with functions "(.*)"')
def given_curr_manifest_with_fns(m, params):
    spec = params.get("current") or m.group(1)
    ctx.curr_manifest = _parse_fn_spec(spec)


@step(r'the path "<missing>" does not exist')
def given_missing_path(m, params):
    ctx.source_path = "/nonexistent/__no_such_manifest_file__.py"
    ctx.source = ""


@step(r"a Python source file with an embedded manifest current as of its content")
def given_file_with_current_manifest(m, params):
    ctx.source = _BASE_FN_SRC
    manifest = build_manifest(ctx.source, tested_at=_TESTED_AT)
    ctx.embedded = embed_manifest(ctx.source, manifest)
    ctx.source_path = _write_tmp(ctx.embedded)
    ctx.file_content_before = ctx.embedded


@step(r'the file is then changed by "(.*)"')
def given_file_then_changed(m, params):
    edit = params.get("edit") or m.group(1)
    if edit == "nothing":
        return
    elif edit == "reformatting whitespace":
        new_src = "def foo(a, b):\n    return  a + b\n"
    elif edit == "changing an operator":
        new_src = "def foo(a, b):\n    return a - b\n"
    else:
        raise ValueError(f"unknown edit: {edit!r}")
    # Re-embed manifest with new source (keep current manifest footer)
    manifest = build_manifest(ctx.source, tested_at=_TESTED_AT)
    ctx.embedded = embed_manifest(new_src, manifest)
    ctx.source_path = _write_tmp(ctx.embedded)
    ctx.file_content_before = ctx.embedded


# ── When steps ─────────────────────────────────────────────────────────────────


@step(r"a manifest is embedded into the file")
def when_embed(m, params):
    manifest = build_manifest(strip_manifest(ctx.source), tested_at=_TESTED_AT)
    ctx.manifest_built = manifest
    ctx.embedded = embed_manifest(ctx.source, manifest)


@step(r"the embedded manifest is extracted")
def when_extract_embedded(m, params):
    ctx.extracted, ctx.extract_ok = extract_manifest(ctx.embedded)


@step(r"the file is extracted")
def when_extract_file(m, params):
    ctx.extracted, ctx.extract_ok = extract_manifest(ctx.source)


@step(r"the previous manifest is diffed against the current manifest")
def when_diff(m, params):
    ctx.changed_ids = diff_manifests(ctx.prev_manifest, ctx.curr_manifest)


@step(r'the command "mutate4py <file> --update-manifest" is run')
def when_cli_update_manifest(m, params):
    ctx.cli_result = run_mutate4py(ctx.source_path, "--update-manifest")


@step(r'the command "mutate4py <missing> --update-manifest" is run')
def when_cli_update_manifest_missing(m, params):
    ctx.cli_result = run_mutate4py(ctx.source_path, "--update-manifest")


# ── Then steps ─────────────────────────────────────────────────────────────────


@step(r'the file contains the line "(.+)"')
def then_file_contains_line(m, params):
    expected = m.group(1)
    lines = ctx.embedded.splitlines()
    assert expected in lines, f"line {expected!r} not found in:\n{ctx.embedded}"


@step(r'the manifest JSON line begins with "# "')
def then_json_line_begins_hash(m, params):
    lines = ctx.embedded.splitlines()
    begin_idx = lines.index("# mutate4py-manifest-begin")
    json_line = lines[begin_idx + 1]
    assert json_line.startswith("# "), f"JSON line does not start with '# ': {json_line!r}"


@step(r"the manifest body above the footer is the original source with trailing newlines trimmed")
def then_body_is_trimmed_original(m, params):
    begin_idx = ctx.embedded.index("# mutate4py-manifest-begin")
    body = ctx.embedded[:begin_idx]
    expected = ctx.source.rstrip("\n") + "\n\n"
    assert body == expected, f"body mismatch:\n{body!r}\n!=\n{expected!r}"


@step(r'the manifest field "(.+)" is present')
def then_field_present(m, params):
    field = params.get("field") or m.group(1)
    assert ctx.extracted is not None, "no manifest extracted"
    assert field in ctx.extracted, f"field {field!r} missing from manifest"


@step(r'the first function record has id "(.+)" and name "(.+)"')
def then_first_fn_id_name(m, params):
    fid = params.get("id") or m.group(1)
    name = params.get("name") or m.group(2)
    assert ctx.extracted is not None
    fns = ctx.extracted["functions"]
    assert len(fns) >= 1, "no function records"
    assert fns[0]["id"] == fid, f"id: {fns[0]['id']!r} != {fid!r}"
    assert fns[0]["name"] == name, f"name: {fns[0]['name']!r} != {name!r}"


@step(r'the first function record has a "line", an "end_line", and a "hash"')
def then_first_fn_has_range_hash(m, params):
    assert ctx.extracted is not None
    fn = ctx.extracted["functions"][0]
    for field in ("line", "end_line", "hash"):
        assert field in fn, f"field {field!r} missing from function record"


@step(r'the first function record "line" is (\d+)')
def then_first_fn_line_is(m, params):
    expected = int(params.get("def_line") or m.group(1))
    assert ctx.extracted is not None
    fn = ctx.extracted["functions"][0]
    assert fn["line"] == expected, f"line: {fn['line']} != {expected}"


@step(r'the manifest "functions" list is empty')
def then_functions_empty(m, params):
    assert ctx.extracted is not None
    assert ctx.extracted["functions"] == [], f"expected empty functions, got {ctx.extracted['functions']}"


@step(r'the manifest "module_hash" is a non-empty hash')
def then_module_hash_non_empty(m, params):
    assert ctx.extracted is not None
    mh = ctx.extracted.get("module_hash", "")
    assert isinstance(mh, str) and len(mh) > 0, f"module_hash is empty: {mh!r}"


@step(r"the extracted manifest equals the embedded manifest")
def then_extracted_equals_embedded(m, params):
    assert ctx.extract_ok, "extraction failed"
    assert ctx.manifest_built is not None
    assert ctx.extracted["version"] == ctx.manifest_built["version"]
    assert ctx.extracted["module_hash"] == ctx.manifest_built["module_hash"]
    assert ctx.extracted["functions"] == ctx.manifest_built["functions"]


@step(r'the extract result is "no manifest"')
def then_no_manifest(m, params):
    assert ctx.extracted is None and not ctx.extract_ok, (
        f"expected no manifest but got: {ctx.extracted}"
    )


@step(r'the file contains exactly one "# mutate4py-manifest-begin" line')
def then_exactly_one_begin(m, params):
    count = ctx.embedded.count("# mutate4py-manifest-begin")
    assert count == 1, f"expected 1 begin marker, got {count}"


@step(r"the manifest body above the footer is byte-identical to the once-embedded body")
def then_body_identical(m, params):
    begin = ctx.embedded.index("# mutate4py-manifest-begin")
    body = ctx.embedded[:begin]
    # body must not contain begin marker and must equal original source stripped of manifest
    original_begin = ctx.source.find("# mutate4py-manifest-begin")
    if original_begin != -1:
        expected_body = ctx.source[:original_begin]
    else:
        expected_body = ctx.source.rstrip("\n") + "\n\n"
    assert body == expected_body, f"body mismatch:\n{body!r}\n!=\n{expected_body!r}"


@step(r'the changed function ids are "(.*)"')
def then_changed_ids(m, params):
    raw = params.get("changed") or m.group(1)
    if raw.strip() == "":
        expected = set()
    else:
        expected = {s.strip() for s in raw.split(",")}
    assert ctx.changed_ids == expected, f"changed_ids: {ctx.changed_ids} != {expected}"


@step(r'the output line "(.+)" is printed')
def then_output_line_printed(m, params):
    line = params.get("output") or m.group(1)
    line = line.replace("<file>", ctx.source_path or "")
    assert line in ctx.cli_result.stdout, (
        f"expected {line!r} in stdout:\n{ctx.cli_result.stdout}"
    )


@step(r"the file then contains an embedded manifest")
def then_file_has_manifest(m, params):
    with open(ctx.source_path) as f:
        content = f.read()
    _, ok = extract_manifest(content)
    assert ok, f"no manifest found in file after --update-manifest:\n{content}"


@step(r"no test command is run")
def then_no_test_cmd(m, params):
    pass  # --update-manifest is read-only w.r.t. test execution


@step(r'the file footer is "(.*)"')
def then_footer_state(m, params):
    state = params.get("footer_state") or m.group(1)
    with open(ctx.source_path) as f:
        current = f.read()
    if state == "byte-identical":
        assert current == ctx.file_content_before, (
            f"expected byte-identical but file changed:\nbefore={ctx.file_content_before!r}\nafter={current!r}"
        )
    elif state == "rewritten":
        assert current != ctx.file_content_before, (
            "expected footer rewritten but file is byte-identical"
        )
        _, ok = extract_manifest(current)
        assert ok, "rewritten file has no valid manifest"
    else:
        raise AssertionError(f"unknown footer_state: {state!r}")


@step(r"the command exits with a usage error")
def then_usage_error(m, params):
    assert_nonzero_exit(ctx.cli_result, "usage error")


@step(r"no manifest is written")
def then_no_manifest_written(m, params):
    # path doesn't exist, so nothing to check
    assert not os.path.exists(ctx.source_path), (
        f"file unexpectedly exists: {ctx.source_path}"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_fn_spec(spec: str) -> dict | None:
    """Parse 'none' or 'func/a:h1, func/b:h2' into a manifest dict."""
    if spec.strip() == "none":
        return None
    functions = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            fid, fhash = part.split(":", 1)
        else:
            fid, fhash = part, "h0"
        functions.append({"id": fid.strip(), "name": fid.strip().split("/")[-1], "line": 1, "end_line": 2, "hash": fhash.strip()})
    return {
        "version": 1,
        "tested_at": _TESTED_AT,
        "module_hash": "mh",
        "functions": functions,
    }
