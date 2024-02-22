#!flask/bin/python
#
# Cache module
#
# Import flask
from flask import Flask
import os 
import shutil

# Import caching
from flask_caching import Cache

import settings

shutil.rmtree(settings.cache_folder, ignore_errors=True)

os.makedirs(settings.cache_folder, exist_ok=True)

# Cache config
cache = Cache(config={'CACHE_TYPE': 'FileSystemCache', "CACHE_DIR": settings.cache_folder, "CACHE_DEFAULT_TIMEOUT": 3600})
