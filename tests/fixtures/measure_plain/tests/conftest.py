import time

import pytest


@pytest.fixture(scope="module")
def slow_resource():
    time.sleep(0.2)
    return 1
