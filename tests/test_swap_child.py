"""Unit tests for _swap_child.py: what a swap-mode child does before pytest
starts, driven in-process over functions built from real sources."""

import os

import pytest

from mutate4py._swap_child import SwapSource, live_functions_of, read_report, swap_child_mode, swap_in

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
def test_a_swap_child_that_reported_a_swap_ran_by_swap():
    assert swap_child_mode(b"swap") == "swap"


@pytest.mark.unit
@pytest.mark.parametrize("report", [b"fresh interpreter", b"", b"sw"])
def test_a_swap_child_that_reported_anything_else_ran_in_a_fresh_interpreter(report):
    # Empty: the child died before it reported, so no swap is claimed.
    assert swap_child_mode(report) == "fresh interpreter"
