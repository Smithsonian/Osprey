#!/usr/bin/env python3
#
# Script to update the Osprey statistics
# https://github.com/Smithsonian/Osprey
#
#
############################################
# Import modules
############################################
import time
from subprocess import run
import random
import sys

# For Postgres
import psycopg2
import psycopg2.extras

# Import settings from settings.py file
import settings

ver = "0.1"


############################################
# Functions
############################################
conn = psycopg2.connect(host=settings.db_host,
                                database=settings.db_db,
                                user=settings.db_user,
                                password=settings.db_password)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
conn.autocommit = True

if len(sys.argv) == 1:
    print("folder_id missing")
elif len(sys.argv) == 2:
    folder_id = sys.argv[1]
else:
    print("Wrong number of args")

############################################
# Run
############################################
try:
    cur.execute("""
        INSERT INTO file_postprocessing
                (file_id, post_results, post_step)
            (SELECT
             file_id,
             0 as post_results,
             'ready_for_dams' as post_step
             FROM
             (
             SELECT
             f.file_id
             FROM
             dams_vfcu_file_view_dpo d,
             files f,
             folders fold,
             projects p
             WHERE
             fold.folder_id = f.folder_id AND
             fold.project_id = p.project_id AND
             d.project_cd = p.process_summary AND
             d.media_file_name = f.file_name || '.tif' AND
             f.folder_id = %(folder_id)s
             )
            a
            ) ON
            CONFLICT(post_step, file_id)
            DO
            UPDATE
            SET
            post_results = 0
        """, {'folder_id': folder_id})
except Exception as error:
    print("Error: {}".format(error))




try:
    cur.execute("""
             UPDATE
                folders
                SET
                delivered_to_dams = 0
                WHERE
                folder_id = %(folder_id)s
        """, {'folder_id': folder_id})
except Exception as error:
    print("Error: {}".format(error))






cur.close()
conn.close()

sys.exit(0)
