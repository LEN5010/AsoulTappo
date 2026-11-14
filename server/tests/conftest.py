import os

# Never touch a real database file from tests; must be set before app.main is imported.
os.environ.setdefault("ASOULTAPPO_DB", ":memory:")

# The example economy (app/economy.py); tests derive their expectations from it, never from the live file.
os.environ.setdefault("ASOULTAPPO_ECONOMY", os.path.join(os.path.dirname(__file__), "..", "economy.example.json"))
