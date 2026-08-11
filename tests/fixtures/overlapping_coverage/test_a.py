from shared import only_a, shared


def test_from_a():
    assert shared() == 1
    assert only_a() == "a"
