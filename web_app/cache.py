#!/usr/bin/env python3
#
# Cache module
#
import os

# Import caching
from flask_caching import Cache

import settings

# Resolve the cache dir relative to the app, not the process CWD, so cron
# scripts and tests that import this module all share the same location.
_cache_dir = settings.cache_folder
if not os.path.isabs(_cache_dir):
    _cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), _cache_dir)

os.makedirs(_cache_dir, exist_ok=True)

# Cache config
cache = Cache(config={'CACHE_TYPE': 'FileSystemCache',
                      "CACHE_DIR": _cache_dir,
                      "CACHE_DEFAULT_TIMEOUT": 3600})
