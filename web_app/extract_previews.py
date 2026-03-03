#!/usr/bin/env python3
# 
import os
import sys
import tarfile
import logging
from time import strftime
from time import localtime
import subprocess
from uuid import UUID
import settings

subprocess.check_call([sys.executable, "-m", "pip", "install", 'mysql-connector-python'])
import mysql.connector


folder_id = sys.argv[1]

# Logging
current_time = strftime("%Y%m%d_%H%M%S", localtime())
logger = logging.getLogger(__name__)
logging.basicConfig(filename='logs/extract_previews_{}.log'.format(current_time), 
            encoding='utf-8',
            format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
                    datefmt='%y-%b-%d %H:%M:%S', 
            level=logging.DEBUG)

logger.info(f"folder_id: {folder_id}")

try:
    folder_id = int(folder_id)
    folder_id = str(folder_id)
    transcription = 0
    folder_id = f"folder{folder_id}"
except:
    try:
        # Allow for UUIDs
        folder_id = UUID(folder_id)
        folder_id = str(folder_id)
        source_id = sys.argv[2]
        source_id = UUID(source_id)
        source_id = str(source_id)
        transcription = 1
    except:
        logger.error(f"folder_id is wrong type: {folder_id}")

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

if transcription == 1:
    res = cur.execute(("SELECT file_transcription_id as file_id FROM transcription_qc WHERE folder_transcription_id = %(folder_id)s and transcription_source_id = %(source_id)s order by file_transcription_id "),
                            {'folder_id': folder_id, 'source_id': source_id})
else:
    res = cur.execute(("SELECT file_id FROM qc_files WHERE folder_id = %(folder_id)s order by file_id "),
                            {'folder_id': folder_id})

files_qc = cur.fetchall()
logger.info("Found {} files to extract".format(len(files_qc)))

for f in files_qc:
    tarimgfile = "static/image_previews/{}/{}_files.tar".format(folder_id, f['file_id'])
    imgfolder = "static/image_previews/{}/".format(folder_id)
    if os.path.isfile(tarimgfile):
        if os.path.isdir("static/image_previews/{}/{}_files".format(folder_id, f['file_id'])) is False:
            logger.info("Extracting {}".format(tarimgfile))
            try:
                with tarfile.open(tarimgfile, "r") as tf:
                    tf.extractall(path=imgfolder)
            except: 
                logger.error("Couln't extract {}".format(tarimgfile))
                sys.exit(1)
        else:
            logger.info("File {} already extracted".format(tarimgfile))
