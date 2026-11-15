"""Unit tests for acceptance/steps/site_discovery_helpers.py."""

import pytest

from acceptance.steps.site_discovery_helpers import assert_warning_line, warning_lines

_SCAN = "Mutation scan: f.py\nTotal mutation sites: 3\nWarning: 3 mutation sites exceeds threshold 2.\n"


@pytest.mark.unit
def test_warning_lines_are_the_lines_that_start_with_warning():
    assert warning_lines(_SCAN) == ["Warning: 3 mutation sites exceeds threshold 2."]


@pytest.mark.unit
def test_warning_lines_ignore_a_line_that_only_mentions_a_warning():
    assert warning_lines("note: Warning: not one\n") == []


@pytest.mark.unit
def test_the_printed_warning_line_must_equal_the_expected_text():
    assert_warning_line(_SCAN, "Warning: 3 mutation sites exceeds threshold 2.")


@pytest.mark.unit
def test_a_different_warning_text_fails():
    with pytest.raises(AssertionError):
        assert_warning_line(_SCAN, "Warning: 3 mutation sites exceeds threshold 3.")


@pytest.mark.unit
def test_a_missing_warning_fails_when_one_is_expected():
    with pytest.raises(AssertionError):
        assert_warning_line("Total mutation sites: 3\n", "Warning: 3 mutation sites exceeds threshold 2.")


@pytest.mark.unit
def test_an_empty_expectation_requires_that_no_warning_printed():
    assert_warning_line("Total mutation sites: 2\n", "")
    with pytest.raises(AssertionError):
        assert_warning_line(_SCAN, "")
