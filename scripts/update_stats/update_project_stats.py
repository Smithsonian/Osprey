#!/usr/bin/env python3
#
# Script to update the Osprey statistics
# https://github.com/Smithsonian/Osprey
#
#

import sys

# MySQL
import pymysql

# Import settings from settings.py file
import settings

ver = "0.2"


if len(sys.argv) == 1:
    print("project_alias missing")
elif len(sys.argv) == 2:
    project_alias = sys.argv[1]
else:
    print("Wrong number of args")


############################################
# Connect
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
    print("Error in connection: {}".format(e))
    sys.exit(1)



query = ("SELECT * FROM projects WHERE project_alias = %(project_alias)s")
res = cur.execute(query, {'project_alias': project_alias})
project = cur.fetchall()

proj = project[0]

query = ("SELECT * FROM folders WHERE project_id = %(project_id)s")
results = cur.execute(query, {'project_id': proj['project_id']})
folders = cur.fetchall()

# for folder in folders:
#     folder_id = folder['folder_id']
#     query = ("with data as (SELECT f.folder_id, COUNT(DISTINCT f.file_id) AS no_files "
#              " FROM files_checks c, files f  WHERE f.folder_id = %(folder_id)s AND f.file_id = c.file_id AND c.check_results = 9) "
#              " UPDATE folders f, data d SET f.file_errors = CASE WHEN d.no_files > 0 THEN 1 ELSE 0 END WHERE f.folder_id = d.folder_id")
#     res = cur.execute(query, {'folder_id': folder_id})
#     res = cur.fetchall()
#     query = (
#         "WITH data AS (SELECT CASE WHEN COUNT(DISTINCT f.file_id) > 0 THEN 1 ELSE 0 END AS no_files, f.folder_id FROM files_checks c, files f"
#         " WHERE f.folder_id = %(folder_id)s AND f.file_id = c.file_id AND c.check_results = 9)"
#         " UPDATE folders f, data d SET f.file_errors = d.no_files "
#         "WHERE f.folder_id = d.folder_id")
#     res = cur.execute(query, {'folder_id': folder_id})
#     res = cur.fetchall()
#     query = ("with data as (SELECT f.folder_id, COUNT(DISTINCT f.file_id) AS no_files "
#              " FROM files_checks c, files f  WHERE f.folder_id = %(folder_id)s AND f.file_id = c.file_id AND c.check_results = 9) "
#              " UPDATE folders f, data d SET f.file_errors = CASE WHEN d.no_files > 0 THEN 1 ELSE 0 END WHERE f.folder_id = d.folder_id")
#     res = cur.execute(query, {'folder_id': folder_id})
#     res = cur.fetchall()
#     # Clear badges
#     res = cur.execute(
#         "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'no_files'",
#         {'folder_id': folder_id})
#     res = cur.fetchall()
#     res = cur.execute(
#         "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'error_files'",
#         {'folder_id': folder_id})
#     res = cur.fetchall()
#     res = cur.execute(
#         "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'qc_status'",
#         {'folder_id': folder_id})
#     res = cur.fetchall()
#     # Badge of no_files
#     res = cur.execute("SELECT COUNT(*) AS no_files FROM files WHERE folder_id = %(folder_id)s",
#                                   {'folder_id': folder_id})
#     no_files = cur.fetchall()
#     if no_files[0]['no_files'] > 0:
#         if no_files[0]['no_files'] == 1:
#             no_folder_files = "1 file"
#         else:
#             no_folder_files = "{} files".format(no_files[0]['no_files'])
#     query = ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
#              " VALUES (%(folder_id)s, 'no_files', 'bg-primary', %(no_files)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
#              " badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
#     res = cur.execute(query, {'folder_id': folder_id, 'no_files': no_folder_files})
#     res = cur.fetchall()
#     # Badge of error files
#     query = ("with data as ("
#              " SELECT f.folder_id, COUNT(DISTINCT f.file_id) AS no_files "
#              " FROM files_checks c, files f  WHERE f.folder_id = %(folder_id)s AND f.file_id = c.file_id AND c.check_results != 0 ) "
#              " UPDATE folders f, data d SET f.file_errors = CASE WHEN d.no_files > 0 THEN 1 ELSE 0 END WHERE f.folder_id = d.folder_id")
#     err_files = cur.execute(query, {'folder_id': folder_id})
#     res = cur.fetchall()
#     no_files = cur.execute("SELECT file_errors FROM folders WHERE folder_id = %(folder_id)s",
#                               {'folder_id': folder_id})
#     no_files = cur.fetchall()
#     if no_files[0]['file_errors'] == 1:
#         query = (
#             "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
#             " VALUES (%(folder_id)s, 'error_files', 'bg-danger', 'Files with errors', CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
#             "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
#     res = cur.execute(query, {'folder_id': folder_id, 'no_files': no_folder_files})
#     res = cur.fetchall()
#     #QC
#     query = ("SELECT * FROM qc_folders WHERE folder_id = %(folder_id)s")
#     folder_qc = cur.execute(query, {'folder_id': folder_id})
#     folder_qc = cur.fetchall()
#     if len(folder_qc) == 0:
#         qc_status = "QC Pending"
#         badge_css = "bg-secondary"
#     else:
#         folder_qc_status = folder_qc[0]['qc_status']
#         if folder_qc_status == 0:
#             qc_status = "QC Passed"
#             badge_css = "bg-success"
#         elif folder_qc_status == 1:
#             qc_status = "QC Failed"
#             badge_css = "bg-danger"
#         elif folder_qc_status == 9:
#             qc_status = "QC Pending"
#             badge_css = "bg-secondary"
#     query = ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
#              " VALUES (%(folder_id)s, 'qc_status', %(badge_css)s, %(qc_status)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(qc_status)s,"
#              "       badge_css = %(badge_css)s, updated_at = CURRENT_TIMESTAMP")
#     res = cur.execute(query, {'qc_status': qc_status, 'badge_css': badge_css, 'folder_id': folder_id})
#     res=cur.fetchall()



# Update DAMS UAN
try:
    query = ("SELECT * FROM projects_settings WHERE project_id = %(project_id)s AND project_setting = 'dams'")
    res = cur.execute(query, {'project_id': project_id})
    dams_process = cur.fetchall()

    dams_code = dams_process[0]['settings_value']


    query = ("with fol as (select folder_id from folders where project_id = %(project_id)s), "
	            " fil as (select f.* from files f, fol where f.folder_id = fol.folder_id) "
                        "  SELECT f.file_id, d.dams_uan " 
                        " FROM dams_cdis_file_status_view_dpo d, fil f, projects p " 
                        " WHERE  "
                        	" p.project_id = %(project_id)s and " 
                            " d.file_name = concat(f.file_name, '.tif') AND " 
                            " d.project_cd = %(dams_code)s AND "
                            " d.to_dams_ingest_dt > p.project_start ")
    cur.execute(query, {'project_id': proj['project_id'], 'dams_code': dams_code})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)



# Set as delivered
try:
    cur.execute("""
        INSERT INTO file_postprocessing (file_id, post_step, post_results)
            (SELECT file_id, 'in_dams', 0
                FROM
                (
                  SELECT
                        f.file_id
                  FROM
                        files f,
                        folders fol
                  WHERE
                        f.folder_id = fol.folder_id AND
                        fol.project_id = %(project_id)s AND
                        f.dams_uan IS NOT NULL
                    ) a
                )
                ON DUPLICATE KEY UPDATE post_results = 0
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)


try:
    cur.execute("""
        INSERT INTO file_postprocessing (file_id, post_step, post_results)
            (SELECT file_id, 'public', 0
                FROM
                (
                  SELECT
                        f.file_id
                  FROM
                        files f,
                        folders fol
                  WHERE
                        f.folder_id = fol.folder_id AND
                        fol.project_id = %(project_id)s AND
                        f.dams_uan IS NOT NULL
                    ) a
                )
                ON DUPLICATE KEY UPDATE post_results = 0
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)




# Set as delivered folder
try:
    cur.execute("""
        WITH files_ok AS (
                SELECT
                    count(f.file_id) as no_files,
                    f.folder_id
                FROM
                    files f,
                    folders fol,
                    file_postprocessing fp
                WHERE
                    fp.post_step = 'in_dams' AND
                    fp.post_results = 0 AND
                    fol.folder_id = f.folder_id AND
                    fol.project_id = %(project_id)s AND
                    fp.file_id = f.file_id
                GROUP BY
                    f.folder_id
            ),
            files_count AS (
                SELECT
                    count(f.file_id) as no_files,
                    f.folder_id
                FROM
                    files f,
                    folders fol
                WHERE
                    fol.folder_id = f.folder_id AND
                    fol.project_id = %(project_id)s
                GROUP BY
                    f.folder_id
            ),
            to_update AS (
                SELECT
                    fc.folder_id
                FROM
                    files_count fc,
                    files_ok ok
                WHERE
                    fc.folder_id = ok.folder_id AND
                    fc.no_files = ok.no_files
            )
        UPDATE folders f
            SET delivered_to_dams = 1
            FROM to_update t
            WHERE f.folder_id = t.folder_id
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)


# Update public images
try:
    cur.execute("""
        with dams_images as (
            SELECT
                f.file_name,
                fol.date,
                fol.project_id
            FROM
                files f,
                folders fol
            WHERE
                f.folder_id = fol.folder_id AND
                dams_uan IS NOT NULL AND
                fol.project_id = %(project_id)s
            ),
        images as (
            SELECT
                count(distinct file_name) as total_img,
                project_id
            FROM
                dams_images
            GROUP BY
                project_id
            )

        UPDATE
            projects_stats p
        SET
            images_public = i.total_img::int,
            updated_at = NOW()
        FROM
            images i
        WHERE
            p.project_id = i.project_id
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)




# clear stats
try:
    cur.execute("""
       delete from projects_stats_detail
        WHERE project_id = %(project_id)s
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)


# daily
try:
    cur.execute("""
        WITH dpo_images AS (
            SELECT
                count(DISTINCT f.file_name) as no_images,
                fol.date,
                fol.project_id
            FROM
                files f,
                folders fol,
                qc_folders q
            WHERE
                f.folder_id = fol.folder_id AND
                fol.folder_id = q.folder_id AND
                q.qc_status = 0 AND
                fol.project_id = %(project_id)s
            GROUP BY
                fol.date,
                fol.project_id
                ),
        dpo_objects AS (
            SELECT
                (i.no_images * p.project_img_2_object) as no_objects,
                i.date
            FROM
                dpo_images i,
                projects p
            WHERE
                p.project_id = i.project_id
                ),
        dateseries AS (
              SELECT date_trunc('day', dd)::date as date,
                      %(project_id)s as project_id
                FROM generate_series
                        ( (select min(date) FROM dpo_images)::timestamp
                        , (select max(date) FROM dpo_images)::timestamp
                        , '1 day'::interval) dd
              )

        INSERT INTO
              projects_stats_detail
              (project_id, time_interval, date, objects_digitized, images_captured)
              (
                SELECT
                  ds.project_id::int,
                  'daily',
                  ds.date,
                  coalesce(o.no_objects, 0),
                  coalesce(i.no_images, 0)
              FROM
                dateseries ds
                    LEFT JOIN dpo_images i ON (ds.date = i.date)
                    LEFT JOIN dpo_objects o ON (ds.date = o.date)
              )
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)


# weekly
try:
    cur.execute("""
        WITH dpo_images AS (
            SELECT
                f.file_name,
                date_trunc('week', fol.date)::date as date,
                fol.project_id
            FROM
                files f,
                folders fol,
                qc_folders q
            WHERE
                f.folder_id = fol.folder_id AND
                fol.folder_id = q.folder_id AND
                q.qc_status = 0 AND
                fol.project_id = %(project_id)s
                ),
        di as (
          SELECT
              count(distinct file_name) as no_images,
              date
          FROM
              dpo_images
          GROUP BY date
        ),
        dateseries AS (
              SELECT DISTINCT date_trunc('week', dd)::date as date
                FROM generate_series
                        ( (select min(date) FROM di)::timestamp
                        , (select max(date) FROM di)::timestamp
                        , '1 day'::interval) dd
              )

        INSERT INTO
              projects_stats_detail
              (project_id, time_interval, date, objects_digitized, images_captured)
              (
                SELECT
                  p.project_id,
                  'weekly',
                  ds.date,
                  coalesce((di.no_images * p.project_img_2_object), 0),
                  coalesce(di.no_images, 0)
              FROM
                dateseries ds
                    LEFT JOIN di ON (ds.date = di.date),
                projects p
                WHERE p.project_id = %(project_id)s
              )
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)




# monthly
try:
    cur.execute("""
        WITH dpo_images AS (
            SELECT
                f.file_name,
                date_trunc('month', fol.date)::date as date,
                fol.project_id
            FROM
                files f,
                folders fol,
                qc_folders q
            WHERE
                f.folder_id = fol.folder_id AND
                fol.folder_id = q.folder_id AND
                q.qc_status = 0 AND
                fol.project_id = %(project_id)s
                ),
        di as (
          SELECT
              count(distinct file_name) as no_images,
              date
          FROM
              dpo_images
          GROUP BY date
        ),
        dateseries AS (
              SELECT DISTINCT date_trunc('month', dd)::date as date
                FROM generate_series
                        ( (select min(date) FROM di)::timestamp
                        , (select max(date) FROM di)::timestamp
                        , '1 day'::interval) dd
              )

        INSERT INTO
              projects_stats_detail
              (project_id, time_interval, date, objects_digitized, images_captured)
              (
                SELECT
                  p.project_id,
                  'monthly',
                  ds.date,
                  coalesce((di.no_images * p.project_img_2_object), 0),
                  coalesce(di.no_images, 0)
              FROM
                dateseries ds
                    LEFT JOIN di ON (ds.date = di.date),
                projects p
                WHERE p.project_id = %(project_id)s
              )
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)




cur.close()
conn.close()

sys.exit(0)
