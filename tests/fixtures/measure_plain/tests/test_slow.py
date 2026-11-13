def test_pays_the_setup(slow_resource):
    assert slow_resource == 1


def test_reuses_the_setup(slow_resource):
    assert slow_resource == 1
