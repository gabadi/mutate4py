"""Minimal Django settings for the issue-05 fixture project — deliberately
small, not a template for a real project."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = "fixture-only-not-a-real-secret"
DEBUG = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "polls",
]

# DB_DIR defaults to BASE_DIR (this file's own directory) so the fixture is
# self-contained when run standalone. Tests that exercise mutate4py's real
# Worker model set MUTATE4PY_FIXTURE_DB_DIR to one shared directory outside
# any Worker's own tree copy — every Worker gets its own copy of this
# settings.py (ADR 0015's tree-copy-per-worker), so a BASE_DIR-relative path
# would land in a different directory per Worker and never collide on its
# own. Pointing every Worker at one shared path models what a real
# Postgres/MySQL NAME (a server-side identifier, not a filesystem path) does
# unconditionally: every Worker targets the same database regardless of
# which copied tree it runs from.
DB_DIR = os.environ.get("MUTATE4PY_FIXTURE_DB_DIR", BASE_DIR)

# File-based (not ":memory:") so pytest-django's per-worker suffix logic
# actually applies (fixtures.py: `_set_suffix_to_test_databases` skips
# sqlite when TEST.NAME is unset, since Django defaults sqlite tests to an
# in-memory db with no collision risk). A file-based test db is what
# reproduces the real per-Worker collision this fixture exists to guard
# against.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(DB_DIR, "db.sqlite3"),
        "TEST": {"NAME": os.path.join(DB_DIR, "test_db.sqlite3")},
    }
}
