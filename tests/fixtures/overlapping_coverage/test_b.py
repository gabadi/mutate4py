from shared import only_b, shared


def test_from_b():
    assert shared() == 1
    assert only_b() == "b"
