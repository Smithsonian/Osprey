#!/usr/bin/env python3
# 
import os
import sys
import mysql.connector
import tarfile
import logging
from time import strftime
from time import localtime

import settings

folder_id = sys.argv[1]

# Logging
current_time = strftime("%Y%m%d_%H%M%S", localtime())
logger = logging.getLogger(__name__)
logging.basicConfig(filename='logs/extract_previews_{}.log'.format(current_time), 
            encoding='utf-8',
            format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
                    datefmt='%y-%b-%d %H:%M:%S', 
            level=logging.DEBUG)


try:
    conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, 
                                autocommit=True, 
                                connection_timeout=60)
    conn.time_zone = '-05:00'
    cur = conn.cursor(dictionary=True)
except mysql.connector.Error as err:
    logger.error(err)
    sys.exit(1)


# Expand the tars for the selected images
logger.info(folder_id)
res = cur.execute(("SELECT file_id FROM qc_files WHERE folder_id = %(folder_id)s order by file_id "),
                        {'folder_id': folder_id})
files_qc = cur.fetchall()
logger.info("Found {} files to extract".format(len(files_qc)))

for f in files_qc:
    tarimgfile = "static/image_previews/folder{}/{}_files.tar".format(folder_id, f['file_id'])
    imgfolder = "static/image_previews/folder{}/".format(folder_id)
    if os.path.isfile(tarimgfile):
        if os.path.isdir("static/image_previews/folder{}/{}_files".format(folder_id, f['file_id'])) is False:
            logger.info("Extracting {}".format(tarimgfile))
            try:
                with tarfile.open(tarimgfile, "r") as tf:
                    tf.extractall(path=imgfolder)
            except: 
                logger.error("Couln't extract {}".format(tarimgfile))
                sys.exit(1)
        else:
            logger.info("File {} already extracted".format(tarimgfile))
