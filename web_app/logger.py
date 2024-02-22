import os
import logging
from time import strftime
from time import localtime

# Logging
current_time = strftime("%Y%m%d_%H%M%S", localtime())

# Create folder if it doesn't exists
os.makedirs('logs', exist_ok=True)

logfile = 'logs/recon_{}.log'.format(current_time)
logging.basicConfig(filename=logfile, filemode='a', level=logging.DEBUG,
                    format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
                    datefmt='%y-%b-%d %H:%M:%S')
logger = logging.getLogger("osprey_webapp")
