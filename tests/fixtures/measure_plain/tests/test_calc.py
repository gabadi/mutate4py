from helpers import twice

import calc


def test_add():
    assert calc.add(1, 2) == 3


def test_sub_one():
    assert calc.sub(3, 1) == 2


def test_sub_two():
    assert calc.sub(twice(2), 1) == 3
