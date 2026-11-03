import os

# Never touch a real database file from tests; must be set before app.main is imported.
os.environ.setdefault("ASOULTAPPO_DB", ":memory:")
