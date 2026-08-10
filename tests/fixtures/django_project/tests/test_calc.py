from calc import is_adult, is_senior


def test_is_adult_true():
    assert is_adult(20) is True


def test_is_adult_false():
    assert is_adult(10) is False


def test_is_adult_boundary():
    assert is_adult(18) is True


def test_is_senior_true():
    assert is_senior(70) is True


def test_is_senior_false():
    assert is_senior(40) is False


def test_is_senior_boundary():
    assert is_senior(65) is True
