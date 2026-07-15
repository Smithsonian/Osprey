import os
import logging
from logging.handlers import RotatingFileHandler
from time import strftime
from time import localtime
import gzip
import shutil
import settings

# Logging
current_time = strftime("%Y%m%d_%H%M%S", localtime())

# Create folder if it doesn't exists
# os.makedirs('logs', exist_ok=True)


# From https://docs.python.org/3/howto/logging-cookbook.html#using-a-rotator-and-namer-to-customize-log-rotation-processing
def rotator(source, dest):
    with open(source, 'rb') as f_in:
        with gzip.open(dest, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    os.remove(source)


def namer(name):
    return name + ".gz"


if settings.env == "prod":
    log_level = logging.ERROR
else:
    log_level = logging.DEBUG

log_format = '%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s'
log_datefmt = '%y-%b-%d %H:%M:%S'

logfile = '{}/ospreyapp_{}.log'.format(settings.log_folder, current_time)
logging.basicConfig(level=log_level,
                    format=log_format,
                    datefmt=log_datefmt,
                    handlers=[RotatingFileHandler(logfile, maxBytes=10000000, backupCount=10)])
logging.rotator = rotator
logging.namer = namer
logger = logging.getLogger("osprey_webapp")

# Dedicated logger for the api/ blueprint, written to its own file/log stream.
api_logfile = '{}/ospreyapi_{}.log'.format(settings.log_folder, current_time)
api_handler = RotatingFileHandler(api_logfile, maxBytes=10000000, backupCount=10)
api_handler.setFormatter(logging.Formatter(log_format, datefmt=log_datefmt))
api_handler.rotator = rotator
api_handler.namer = namer

api_logger = logging.getLogger("osprey_api")
api_logger.setLevel(log_level)
api_logger.addHandler(api_handler)
api_logger.propagate = False
