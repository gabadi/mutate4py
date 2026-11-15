"""Unit tests for _pytest_argv.py: how a pytest argv reads, token by token."""

import pytest

from mutate4py._pytest_argv import FLAG, POSITIONAL, VALUE, VALUE_OPTIONS, flag_tokens, positional_tokens, token_roles


@pytest.mark.unit
@pytest.mark.parametrize(
    ("argv", "roles"),
    [
        pytest.param(["-k", "tests"], [FLAG, VALUE], id="separate-value"),
        pytest.param(["-m", "not system"], [FLAG, VALUE], id="marker-expression"),
        pytest.param(["-k", "-x"], [FLAG, VALUE], id="value-that-looks-like-a-flag"),
        pytest.param(["-p", "no:x", "tests"], [FLAG, VALUE, POSITIONAL], id="plugin-then-path"),
        pytest.param(["-q", "tests/test_a.py::test_a"], [FLAG, POSITIONAL], id="bare-switch-then-nodeid"),
        pytest.param(["--rootdir=sub", "tests"], [FLAG, POSITIONAL], id="attached-value"),
        pytest.param(["-kexpr", "tests"], [FLAG, POSITIONAL], id="attached-short-value"),
        pytest.param(["-k"], [FLAG], id="value-option-without-a-value"),
    ],
)
def test_token_roles(argv, roles):
    assert token_roles(argv) == roles


@pytest.mark.unit
@pytest.mark.parametrize("option", sorted(VALUE_OPTIONS))
def test_every_value_option_takes_the_next_token_as_its_value(option):
    assert positional_tokens([option, "tests"]) == []


@pytest.mark.unit
def test_positional_tokens_are_the_arguments_that_are_not_flags_or_option_values():
    argv = ["-k", "src", "-p", "no:x", "tests/test_a.py", "-q", "tests"]

    assert positional_tokens(argv) == ["tests/test_a.py", "tests"]


@pytest.mark.unit
def test_flag_tokens_are_the_flags_value_options_included_and_their_values_excluded():
    argv = ["-k", "src", "-p", "no:x", "tests/test_a.py", "-q", "--rootdir=sub"]

    assert flag_tokens(argv) == ["-k", "-p", "-q", "--rootdir=sub"]
