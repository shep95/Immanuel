import pytest

from immanuel.db import Database


@pytest.fixture()
def db():
    d = Database(":memory:")
    yield d
    d.close()
