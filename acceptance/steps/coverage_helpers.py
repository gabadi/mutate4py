"""Pure helpers for coverage acceptance step files — fully testable."""

import os
import stat


def _parse_line_set(lines_str: str) -> set[int]:
    return {int(n.strip()) for n in lines_str.split(",") if n.strip()}


def _build_source_lines(site_lines: set[int], site_expr: str) -> str:
    max_line = max(site_lines) if site_lines else 0
    rows = [site_expr if ln in site_lines else "" for ln in range(1, max_line + 1)]
    return "\n".join(rows) + "\n"


def make_source_with_sites_on_lines(lines_str: str) -> str:
    """Return Python source with `x = a + b` on each comma-separated line number."""
    site_lines = _parse_line_set(lines_str) if lines_str.strip() else set()
    return _build_source_lines(site_lines, "x = a + b")


def make_calc_source(lines_str: str) -> str:
    """Return Python source with `x = a > b` on each comma-separated line number."""
    return _build_source_lines(_parse_line_set(lines_str), "x = a > b")


def make_lcov(sf_path: str, covered_lines: set[int]) -> str:
    """Return an LCOV text block for sf_path with DA:ln,1 for each covered line."""
    lines = [f"SF:{sf_path}"]
    for ln in sorted(covered_lines):
        lines.append(f"DA:{ln},1")
    lines.append("end_of_record")
    return "\n".join(lines) + "\n"


def make_lcov_da_zero(sf_path: str, line: int) -> str:
    """Return an LCOV block with a single DA:<line>,0 (zero-count, uncovered) record."""
    return f"SF:{sf_path}\nDA:{line},0\nend_of_record\n"


def make_lcov_brda_only(sf_path: str, line: int) -> str:
    """Return an LCOV block with only a BRDA record (no DA) for the given line."""
    return f"SF:{sf_path}\nBRDA:{line},0,0,1\nend_of_record\n"


def make_lcov_single_da(sf: str, line: int) -> str:
    """Return an LCOV block with a single DA:<line>,1 record for the given SF."""
    return f"SF:{sf}\nDA:{line},1\nend_of_record\n"


def make_noop_script(script_path: str) -> str:
    """Write a no-op shell script to script_path and return the path."""
    import stat as _stat
    with open(script_path, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(script_path, os.stat(script_path).st_mode | _stat.S_IEXEC)
    return script_path


def assert_stdout_contains(result, text: str) -> None:
    assert text in result.stdout, (
        f"expected {text!r} in stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def assert_stdout_not_contains(result, text: str) -> None:
    assert text not in result.stdout, (
        f"unexpected {text!r} found in stdout:\n{result.stdout}"
    )


def assert_exit_zero(result) -> None:
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def assert_exit_nonzero(result) -> None:
    assert result.returncode != 0, (
        f"expected non-zero exit, got 0\nstdout:\n{result.stdout}"
    )


def assert_baseline_scan(result, expected_count: int) -> None:
    assert result.returncode == 0, f"baseline scan failed:\n{result.stderr}"
    assert f"Total mutation sites: {expected_count}" in result.stdout, (
        f"baseline expected {expected_count} sites; got:\n{result.stdout}"
    )


def step_param(m, params: dict, key: str) -> str:
    """Return params[key] if present, else m.group(1) — standard step param lookup."""
    return params.get(key) or m.group(1)


def resolve_sf_path(sf_key: str, source_path: str) -> str:
    """Resolve an SF path token to a concrete path string.

    Tokens:
      "absolute-suffix"  → the source_path itself (absolute)
      "relative-suffix"  → basename of source_path (suffix of abs)
      anything else      → returned unchanged
    """
    if sf_key == "absolute-suffix":
        return source_path
    if sf_key == "relative-suffix":
        return os.path.basename(source_path)
    return sf_key


def write_counter_script(script_path: str, counter_path: str, lcov_path: str, lcov_content: str) -> None:
    """Write a shell script that appends one byte to counter_path and writes lcov_content to lcov_path."""
    with open(script_path, "w") as f:
        f.write("#!/bin/sh\n")
        f.write(f"printf 'x' >> {counter_path}\n")
        f.write(f"cat > {lcov_path} << 'LCOV_EOF'\n")
        f.write(lcov_content)
        f.write("LCOV_EOF\n")
    os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IEXEC)


def assert_cmd_ran_n_times(tmpdir: str, expected: int) -> None:
    """Assert that the coverage command counter log has exactly `expected` bytes."""
    counter_path = os.path.join(tmpdir, "cov_runs.log")
    if expected == 0:
        assert not os.path.exists(counter_path), (
            f"expected 0 runs but counter file exists at {counter_path}"
        )
        return
    assert os.path.exists(counter_path), (
        f"expected {expected} runs but counter file missing at {counter_path}"
    )
    with open(counter_path) as f:
        content = f.read()
    assert len(content) == expected, (
        f"expected {expected} run(s), counter file has {len(content)} byte(s): {content!r}"
    )


def substitute_cmd_placeholders(
    flags_str: str,
    tmpdir: str,
    cov_cmd: str | None,
    source_path: str | None = None,
) -> str:
    """Replace CMD/cov.info placeholders in a flags string with concrete values."""
    if "CMD" in flags_str and cov_cmd:
        flags_str = flags_str.replace("CMD", cov_cmd)
    if "cov.info" in flags_str and "--lcov" in flags_str:
        flags_str = flags_str.replace("cov.info", os.path.join(tmpdir, "cov.info"))
    return flags_str


def _replace_cmd_tokens(cmd_str: str, cov_cmd: str | None) -> str:
    if cov_cmd and "CMD" in cmd_str:
        cmd_str = cmd_str.replace("CMD", cov_cmd)
    if cov_cmd and "'<that command>'" in cmd_str:
        cmd_str = cmd_str.replace("'<that command>'", cov_cmd)
    return cmd_str


def _replace_path_tokens(cmd_str: str, tmpdir: str, calc_path: str | None) -> str:
    if calc_path and "<abspath>/calc.py" in cmd_str:
        cmd_str = cmd_str.replace("<abspath>/calc.py", calc_path)
    elif calc_path and "calc.py" in cmd_str:
        cmd_str = cmd_str.replace("calc.py", calc_path)
    if "--lcov cov.info" in cmd_str:
        cmd_str = cmd_str.replace("--lcov cov.info", f"--lcov {os.path.join(tmpdir, 'cov.info')}")
    return cmd_str


def substitute_qa_cmd_placeholders(
    cmd_str: str,
    tmpdir: str,
    cov_cmd: str | None,
    calc_path: str | None,
) -> str:
    """Replace placeholders in QA when-step command strings."""
    cmd_str = _replace_cmd_tokens(cmd_str, cov_cmd)
    return _replace_path_tokens(cmd_str, tmpdir, calc_path)
