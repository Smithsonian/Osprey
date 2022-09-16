import sys, os
import logging
logging.basicConfig(stream=sys.stderr)
sys.path.insert(0, '/var/www/app')

os.chdir('/var/www/app')

from app import app as application
