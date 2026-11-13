"""Unit tests for _fork_child.py: what a forked child decides before pytest
starts, driven in-process over functions built from real sources."""

import os

import pytest

from mutate4py._fork_child import (
    SwapSource,
    child_mode,
    live_functions_of,
    read_report,
    report_mode,
    reported_mode,
    swap_in,
    swap_side,
)

_CLEAN = "def add(a, b):\n    return a + b\n"


def _load(source: str, filename: str) -> dict:
    namespace: dict = {}
    exec(compile(source, filename, "exec"), namespace)
    return namespace


def _guarded(tmp_path, source: str) -> str:
    path = tmp_path / "calc.py"
    path.write_text(source)
    return str(path)


@pytest.mark.unit
def test_a_body_change_is_swapped_into_the_live_function(tmp_path):
    path = _guarded(tmp_path, "def add(a, b):\n    return a - b\n")
    namespace = _load(_CLEAN, path)

    mode = swap_in(SwapSource(_CLEAN, path, frozenset()), path, [namespace["add"]])

    assert mode == "swap"
    assert namespace["add"](5, 3) == 2


@pytest.mark.unit
def test_a_body_that_ran_at_import_runs_in_a_fresh_interpreter(tmp_path):
    path = _guarded(tmp_path, "def add(a, b):\n    return a - b\n")
    namespace = _load(_CLEAN, path)

    mode = swap_in(SwapSource(_CLEAN, path, frozenset({2})), path, [namespace["add"]])

    assert mode == "fresh interpreter"
    assert namespace["add"](5, 3) == 8


@pytest.mark.unit
def test_a_swap_with_no_live_function_runs_in_a_fresh_interpreter(tmp_path):
    path = _guarded(tmp_path, "def add(a, b):\n    return a - b\n")

    assert swap_in(SwapSource(_CLEAN, path, frozenset()), path, []) == "fresh interpreter"


@pytest.mark.unit
def test_a_mutant_that_does_not_compile_runs_in_a_fresh_interpreter(tmp_path):
    path = _guarded(tmp_path, "def add(a, b):\n    return a +\n")
    namespace = _load(_CLEAN, path)

    assert swap_in(SwapSource(_CLEAN, path, frozenset()), path, [namespace["add"]]) == "fresh interpreter"


@pytest.mark.unit
def test_live_functions_are_the_ones_whose_code_comes_from_the_file_by_real_path(tmp_path):
    path = _guarded(tmp_path, _CLEAN)
    link = tmp_path / "link.py"
    link.symlink_to(path)
    namespace = _load(_CLEAN, str(link))
    other = _load(_CLEAN, str(tmp_path / "other.py"))

    found = live_functions_of(path)

    assert namespace["add"] in found
    assert other["add"] not in found


@pytest.mark.unit
def test_a_report_is_read_back_without_waiting_for_a_writer_left_open():
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"swap")
    assert read_report(read_fd) == b"swap"
    read_fd, other_write_fd = os.pipe()
    try:
        assert read_report(read_fd) == b""
    finally:
        os.close(write_fd)
        os.close(other_write_fd)


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["fresh import", "swap", "fresh interpreter"])
def test_a_reported_mode_reads_back_as_itself(mode):
    read_fd, write_fd = os.pipe()
    report_mode(write_fd, mode)
    assert reported_mode(read_report(read_fd)) == mode


@pytest.mark.unit
@pytest.mark.parametrize("report", [b"", b"sw", b"\xff"])
def test_any_other_report_counts_as_a_fresh_interpreter(report):
    # Empty: the child died before it reported, so no in-process run is claimed.
    assert reported_mode(report) == "fresh interpreter"


@pytest.mark.unit
def test_a_fresh_import_file_runs_by_fresh_import_and_a_harness_file_in_a_fresh_interpreter(tmp_path):
    path = _guarded(tmp_path, _CLEAN)
    source = SwapSource("", path, frozenset())
    assert child_mode("fresh import", source, path, []) == "fresh import"
    assert child_mode("harness", source, path, []) == "fresh interpreter"


@pytest.mark.unit
def test_a_swap_file_runs_by_swap_when_the_swap_applies(tmp_path):
    path = _guarded(tmp_path, "def add(a, b):\n    return a - b\n")
    namespace = _load(_CLEAN, path)

    assert child_mode("swap", SwapSource(_CLEAN, path, frozenset()), path, [namespace["add"]]) == "swap"
    assert namespace["add"](5, 3) == 2


@pytest.mark.unit
def test_the_swap_side_of_a_swap_file_is_its_clean_source_and_live_functions(tmp_path):
    path = _guarded(tmp_path, _CLEAN)
    link = tmp_path / "link.py"
    link.symlink_to(path)
    namespace = _load(_CLEAN, str(link))

    source, live = swap_side("swap", path, frozenset({4}))

    assert source == SwapSource(_CLEAN, str(link), frozenset({4}))
    assert namespace["add"] in live


@pytest.mark.unit
def test_the_swap_side_of_a_swap_file_with_no_live_function_compiles_under_its_own_path(tmp_path):
    path = _guarded(tmp_path, _CLEAN)
    assert swap_side("swap", path, frozenset()) == (SwapSource(_CLEAN, path, frozenset()), [])


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["fresh import", "harness"])
def test_a_file_not_in_swap_mode_has_no_swap_side(tmp_path, mode):
    path = _guarded(tmp_path, _CLEAN)
    _load(_CLEAN, path)
    assert swap_side(mode, path, frozenset({1})) == (SwapSource("", path, frozenset({1})), [])


@pytest.mark.unit
def test_a_swap_source_is_immutable():
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        SwapSource(_CLEAN, "calc.py", frozenset()).clean_source = ""
