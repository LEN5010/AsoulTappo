import os
import sys

import pytest

# Never touch a real database file from tests; must be set before app.main is imported.
os.environ.setdefault("ASOULTAPPO_DB", ":memory:")

# The example economy (app/economy.py); tests derive their expectations from it, never from the live file.
os.environ.setdefault("ASOULTAPPO_ECONOMY", os.path.join(os.path.dirname(__file__), "..", "economy.example.json"))


def _forget_kept_rooms() -> None:
    main = sys.modules.get("app.main")
    if main is not None:
        main.manager.restoring.clear()


@pytest.fixture(autouse=True)
def _no_kept_rooms_between_tests():
    """The app's one room manager keeps a room whose last member left (rooms.EMPTY_SECONDS), and rooms of a test
    empty when it ends: each test starts without those of the tests before it. app.main is not imported for it."""
    _forget_kept_rooms()
    yield
    _forget_kept_rooms()
