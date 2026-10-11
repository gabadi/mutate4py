from calc import is_adult, is_senior


def test_is_adult_boundary():
    assert is_adult(18)
    assert not is_adult(17)


def test_is_senior_boundary():
    assert is_senior(65)
    assert not is_senior(64)
