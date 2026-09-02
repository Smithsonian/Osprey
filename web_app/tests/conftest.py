"""Shared test setup.

Stubs the settings module (when no local settings.py exists) and the DB
layer before any application import, so the suite runs in clean checkouts
without MySQL, credentials, or a database.
"""

import importlib.machinery
import importlib.util
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parent.parent

# settings.py is gitignored; fall back to the template with tmp log/cache dirs.
try:
    import settings  # noqa: F401
except Exception:
    loader = importlib.machinery.SourceFileLoader(
        'settings', str(_ROOT / 'settings.py.template')
    )
    spec = importlib.util.spec_from_loader('settings', loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    _tmp = Path(tempfile.mkdtemp(prefix='osprey_test_'))
    (_tmp / 'logs').mkdir()
    (_tmp / 'cache').mkdir()
    mod.log_folder = str(_tmp / 'logs')
    mod.cache_folder = str(_tmp / 'cache')
    sys.modules['settings'] = mod

# Stub the DB layer before osprey.services/app imports: the test env may lack
# mysql.connector, and tests must never touch a real database.
if 'osprey.db' not in sys.modules:
    _db = types.ModuleType('osprey.db')
    _db.run_query = MagicMock()
    _db.query_database_insert = MagicMock()
    _db.executemany = MagicMock()
    _db.init_db = MagicMock()

    class DatabasePoolError(Exception):
        pass

    _db.DatabasePoolError = DatabasePoolError
    sys.modules['osprey.db'] = _db
