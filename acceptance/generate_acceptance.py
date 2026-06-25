"""Acceptance entrypoint generator.

Reads a gherkin-parser JSON output file and emits a Python test module that
loads the IR at runtime (so gherkin-mutator can supply mutated JSON without
regenerating tests).

Usage: python acceptance/generate_acceptance.py <parsed.json> <steps_module> <out_dir>
"""
import hashlib
import json
import os
import re
import sys


def sanitize(name: str) -> str:
    return re.sub(r"\W+", "_", name).strip("_").lower()[:60]


def _feature_metadata_name(feature_path: str) -> str:
    s = feature_path.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s + ".json"


def generate(parsed: dict, steps_module: str, feature_stem: str, ir_path: str) -> str:
    scenarios = parsed.get("scenarios", [])

    lines = [
        "import json, os, re, sys",
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))",
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))",
        f"from acceptance.steps.{steps_module} import run_step",
        "",
        "# Load IR at runtime so mutated JSON can be supplied via APS_FEATURE_JSON",
        "_ir_path = os.environ.get('APS_FEATURE_JSON') or " + repr(ir_path),
        "with open(_ir_path) as _f:",
        "    _ir = json.load(_f)",
        "_background = _ir.get('background', [])",
        "_scenarios = _ir.get('scenarios', [])",
        "",
    ]

    test_fns: list[str] = []
    for s_idx, scenario in enumerate(scenarios):
        name = scenario["name"]
        examples = scenario.get("examples") or [{}]
        for e_idx, _ in enumerate(examples):
            fn_name = f"test_{sanitize(name)}_{e_idx}"
            lines.append(f"def {fn_name}():")
            lines.append(f'    """Scenario: {name} — example {e_idx}"""')
            lines.append(f"    _s = _scenarios[{s_idx}]")
            lines.append(f"    _ex = _s['examples'][{e_idx}] if _s.get('examples') else {{}}")
            lines.append(f"    for _st in _background:")
            lines.append(f"        run_step(_st['keyword'], _st['text'], _ex)")
            lines.append(f"    for _st in _s['steps']:")
            lines.append(f"        _txt = _st['text']")
            lines.append(f"        for _k, _v in _ex.items():")
            lines.append(f"            _txt = _txt.replace('<' + _k + '>', _v)")
            lines.append(f"        run_step(_st['keyword'], _txt, _ex)")
            lines.append("")
            test_fns.append(fn_name)

    lines.append("if __name__ == '__main__':")
    lines.append("    import traceback")
    lines.append("    passed = failed = 0")
    for fn in test_fns:
        lines.append(f"    try:")
        lines.append(f"        {fn}()")
        lines.append(f"        print('PASS {fn}')")
        lines.append(f"        passed += 1")
        lines.append(f"    except Exception as e:")
        lines.append(f"        print(f'FAIL {fn}: {{e}}')")
        lines.append(f"        traceback.print_exc()")
        lines.append(f"        failed += 1")
    lines.append("    print(f'\\n{passed} passed, {failed} failed')")
    lines.append("    sys.exit(0 if failed == 0 else 1)")
    lines.append("")

    return "\n".join(lines)


def _impl_hash(paths: list[str]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        with open(p, "rb") as f:
            h.update(f.read())
    return "sha256:" + h.hexdigest()


def main():
    if len(sys.argv) < 4:
        print(f"usage: {sys.argv[0]} <parsed.json> <steps_module> <out_dir> [feature_path]")
        sys.exit(1)

    parsed_path = sys.argv[1]
    steps_module = sys.argv[2]
    out_dir = sys.argv[3]
    # optional: the original .feature path, for stable metadata naming
    explicit_feature_path = sys.argv[4] if len(sys.argv) > 4 else None

    with open(parsed_path) as f:
        parsed = json.load(f)

    feature_path = explicit_feature_path or parsed.get("feature_path", parsed_path)
    feature_stem = os.path.basename(feature_path).replace(".feature", "") if explicit_feature_path else os.path.basename(parsed_path).replace("_parsed.json", "").replace(".json", "")
    ir_path = os.path.abspath(parsed_path)

    code = generate(parsed, steps_module, feature_stem, ir_path)

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{feature_stem}_acceptance.py")
    with open(out_path, "w") as f:
        f.write(code)
    print(f"Generated: {out_path}")

    impl_hash = _impl_hash([out_path])

    meta_dir = os.path.join(out_dir, "metadata")
    os.makedirs(meta_dir, exist_ok=True)
    meta_name = _feature_metadata_name(feature_path)
    meta_path = os.path.join(meta_dir, meta_name)
    metadata = {
        "schema_version": 1,
        "feature_path": feature_path,
        "ir_path": ir_path,
        "implementation_hash": impl_hash,
        "hash_scope": "generated_files",
        "generated_files": [out_path],
    }
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata:  {meta_path}")


if __name__ == "__main__":
    main()
