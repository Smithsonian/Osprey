#!/usr/bin/env python3
#
# Script to update the Osprey statistics
# https://github.com/Smithsonian/Osprey
#
#
############################################
# Import modules
############################################
# import time
# from subprocess import run
# import random
import sys

# MySQL
import pymysql

# Import settings from settings.py file
import settings

ver = "0.1"


if len(sys.argv) == 1:
    print("folder_id missing")
elif len(sys.argv) == 2:
    folder_id = sys.argv[1]
else:
    print("Wrong number of args")

############################################
# Connect
############################################
try:
    conn = pymysql.connect(host=settings.host,
                           user=settings.user,
                           passwd=settings.password,
                           database=settings.database,
                           port=settings.port,
                           charset='utf8mb4',
                           cursorclass=pymysql.cursors.DictCursor,
                           autocommit=True)
    cur = conn.cursor()
except pymysql.Error as e:
    print('System error: {}'.format(e))
    sys.exit(1)


############################################
# Run
############################################
try:
    cur.execute("""
             DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'dams_status'
        """, {'folder_id': folder_id})
except Exception as error:
    print("Error: {}".format(error))

try:
    cur.execute(
        "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text) VALUES (%(folder_id)s, 'dams_status', 'bg-secondary', 'Ready for DAMS')",
        {'folder_id': folder_id})
except Exception as error:
    print("Error: {}".format(error))


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
                file_id
             FROM
                files
             WHERE
                folder_id = %(folder_id)s
             )
            a
            ) ON
            DUPLICATE KEY UPDATE
            post_results = 0
        """, {'folder_id': folder_id})
except Exception as error:
    print("Error: {}".format(error))



try:
    cur.execute("""
            UPDATE
                files f,
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
                    d.project_cd = p.dams_project_cd AND
                    d.file_name = CONCAT(f.file_name, '.tif') AND
                    f.folder_id =   %(folder_id)s
                ) d
                SET
                f.dams_uan = d.dams_uan
                WHERE
                f.file_id = d.file_id""", {'folder_id': folder_id})
except Exception as error:
    print("Error: {}".format(error))




try:
    cur.execute("""
        INSERT INTO file_postprocessing
                (file_id, post_results, post_step)
            (SELECT
             file_id,
             0 as post_results,
             'in_dams' as post_step
             FROM
             (
             SELECT
                file_id
             FROM
                files
             WHERE
                folder_id = %(folder_id)s AND 
                dams_uan != '' AND dams_uan IS NOT NULL
             )
            a
            ) ON
            DUPLICATE KEY UPDATE
            post_results = 0
        """, {'folder_id': folder_id})
except Exception as error:
    print("Error: {}".format(error))





cur.execute("""
             SELECT COUNT(*) as no_files FROM files WHERE folder_id = %(folder_id)s AND dams_uan != '' AND dams_uan IS NOT NULL
        """, {'folder_id': folder_id})
no_files_ready = cur.fetchall()

cur.execute("""
             SELECT COUNT(*) as no_files FROM files WHERE folder_id = %(folder_id)s AND (dams_uan = '' OR dams_uan IS NULL)
        """, {'folder_id': folder_id})
no_files_pending = cur.fetchall()

if no_files_ready[0]['no_files'] > 0 and no_files_pending[0]['no_files'] == 0:
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

    try:
        cur.execute("""
                 DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'dams_status'
            """, {'folder_id': folder_id})
    except Exception as error:
        print("Error: {}".format(error))

    try:
        cur.execute(
            "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text) VALUES (%(folder_id)s, 'dams_status', 'bg-success', 'Delivered to DAMS')",
            {'folder_id': folder_id})
    except Exception as error:
        print("Error: {}".format(error))





cur.close()
conn.close()

sys.exit(0)
