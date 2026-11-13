import pytest

from calc import is_adult, is_senior
from polls.models import Question

pytestmark = pytest.mark.django_db


def test_is_popular_true():
    q = Question.objects.create(text="q", votes=20)
    assert q.is_popular() is True


def test_is_popular_false():
    q = Question.objects.create(text="q", votes=5)
    assert q.is_popular() is False


def test_is_popular_boundary():
    q = Question.objects.create(text="q", votes=10)
    assert q.is_popular() is False


def test_calc_thresholds_hold_alongside_a_database_write():
    """Covers calc.py's two thresholds from a test that touches the database.

    A narrowed Mutant runs only the tests that cover its line, so without a
    DB-using test on calc.py the per-Worker test databases are never created.
    """
    Question.objects.create(text="q", votes=10)
    assert is_adult(18) is True
    assert is_senior(65) is True
