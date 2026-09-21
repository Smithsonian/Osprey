import os
import logging
from logging.handlers import WatchedFileHandler
import settings

# Only an explicit "dev" is verbose. prod, staging or a typo stay at WARNING.
if settings.env == "dev":
    log_level = logging.DEBUG
else:
    log_level = logging.WARNING

log_format = '%(levelname)s | %(asctime)s | %(process)d | %(filename)s:%(lineno)s | %(message)s'
log_datefmt = '%y-%b-%d %H:%M:%S'

# Fails fast at import if the folder can't be created (e.g. permissions).
os.makedirs(settings.log_folder, exist_ok=True)


def make_handler(filename):
    """File handler with a fixed name; rotation is done by logrotate (see README).

    WatchedFileHandler reopens the file after logrotate moves it, so all
    workers and scripts can append to the same file. delay=True avoids
    creating empty files when a script only imports this module.
    """
    handler = WatchedFileHandler(os.path.join(settings.log_folder, filename), delay=True)
    handler.setFormatter(logging.Formatter(log_format, datefmt=log_datefmt))
    return handler


# Root stays at WARNING so third-party libraries stay quiet; the osprey
# loggers below use log_level. Flask's app.logger propagates to this handler.
app_log_handler = make_handler('ospreyapp.log')
logging.basicConfig(level=logging.WARNING, handlers=[app_log_handler])
logger = logging.getLogger("osprey_webapp")
logger.setLevel(log_level)

# Dedicated logger for the api/ blueprint, written to its own file/log stream.
api_logger = logging.getLogger("osprey_api")
api_logger.setLevel(log_level)
api_logger.addHandler(make_handler('ospreyapi.log'))
api_logger.propagate = False
