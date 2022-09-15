#!/usr/bin/env python3
#
# Script to update the Osprey statistics
# https://github.com/Smithsonian/Osprey
#
## Special cause we don't have all files in the system

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
            INSERT
                INTO
                file_postprocessing
                (file_id, post_results, post_step)
                (SELECT
                 file_id,
                 0 as post_results,
                 'in_dams' as post_step
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
                 f.folder_id =
                 %(folder_id)s
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
            INSERT
                INTO
                file_postprocessing
                (file_id, post_results, post_step)
                (SELECT
                 file_id,
                 0 as post_results,
                 'ingested_emu' as post_step
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
                 f.folder_id =
                 %(folder_id)s
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
            INSERT
                INTO
                file_postprocessing
                (file_id, post_results, post_step)
                (SELECT
                 file_id,
                 0 as post_results,
                 'public' as post_step
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
                 f.folder_id =
                 %(folder_id)s
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



#
# cur.execute("SELECT project_id FROM folders WHERE folder_id = %(folder_id)s", {'folder_id': folder_id})
# project_id = cur.fetchone()['project_id']
#
#
# try:
#     cur.execute("""
#              UPDATE
#                 projects_stats SET images_public = a.total
#                 FROM
#                 (
#                     SELECT
#                         count(f.file_id) as total
#                     FROM
#                         files f,
#                         file_postprocessing fp,
#                         folders fold,
#                         projects p
#                     WHERE
#                         f.folder_id = fold.folder_id AND
#                         fold.project_id = p.project_id AND
#                         p.project_id = %(project_id)s AND
#                         fp.post_step = 'public' AND
#                         fp.post_results = 0 AND
#                         f.file_id = fp.file_id
#                 ) a
#                 WHERE project_id = %(project_id)s
#         """, {'project_id': project_id})
# except Exception as error:
#     print("Error: {}".format(error))



try:
    cur.execute("""
             UPDATE
                files
                f
                SET
                dams_uan = d.dams_uan
                FROM
                (
                    SELECT
                    f.file_id,
                    d.dams_uan
                    FROM
                    dams_cdis_file_status_view_dpo d,
                    files f,
                    folders fold,
                    projects p
                    WHERE
                    fold.folder_id = f.folder_id AND
                    fold.project_id = p.project_id AND
                    d.project_cd = p.process_summary AND
                    d.file_name = f.file_name || '.tif' AND
                    f.folder_id =   %(folder_id)s
                )
                d
                WHERE
                f.file_id = d.file_id
        """, {'folder_id': folder_id})
except Exception as error:
    print("Error: {}".format(error))







try:
    cur.execute("""
             UPDATE
                folders
                SET
                delivered_to_dams = 1
                WHERE
                folder_id = %(folder_id)s
        """, {'folder_id': folder_id})
except Exception as error:
    print("Error: {}".format(error))




try:
    cur.execute("""
             INSERT
        INTO
        qc_folders
        (folder_id, qc_status, qc_by, qc_ip)
        VALUES
        (%(folder_id)s, 0, 100, '127.0.0.1')
        ON
        CONFLICT(folder_id)
        DO
        NOTHING
                """, {'folder_id': folder_id})
except Exception as error:
            print("Error: {}".format(error))




cur.close()
conn.close()

sys.exit(0)
