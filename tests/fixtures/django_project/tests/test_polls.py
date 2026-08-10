import pytest

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
