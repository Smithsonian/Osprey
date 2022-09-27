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
    print("project_id missing")
elif len(sys.argv) == 2:
    project_id = sys.argv[1]
else:
    print("Wrong number of args")

############################################
# Run
############################################
#Update QC-passed images
try:
    cur.execute("""
        WITH dpo_images AS 
          (
            SELECT
                count(f.file_name) as no_images,
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
        total_images AS (
            SELECT 
                sum(i.no_images)::int as total_img,
                project_id
            FROM 
                dpo_images i
            GROUP BY 
                project_id 
            ),
        total_obj AS (
            SELECT 
                sum(o.no_objects)::int as total_obj
            FROM 
                dpo_objects o
            )
        UPDATE
            projects_stats p 
        SET
            objects_digitized = o.total_obj,
            images_taken = i.total_img,
            updated_at = NOW()
        FROM
            total_images i, 
            total_obj o
        WHERE p.project_id = i.project_id
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))
    sys.exit(1)


# Update DAMS UAN
try:
    cur.execute("""
        UPDATE files f SET dams_uan = d.dams_uan
            FROM
            (
            SELECT
                f.file_id,
                d.dams_uan
            FROM
                dams_cdis_file_status_view_dpo d,
                files f,
                folders fol,
                projects p 
            WHERE
                d.file_name = f.file_name || '.tif' AND
                f.folder_id = fol.folder_id AND
                fol.project_id = %(project_id)s AND 
                p.process_summary = d.project_cd 
                 ) d
            WHERE f.file_id = d.file_id
        """, {'project_id': project_id})
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
                        dams_cdis_file_status_view_dpo d,
                        folders fol,
                        projects p 
                  WHERE
                        d.file_name = f.file_name || '.tif' AND
                        f.folder_id = fol.folder_id AND
                        fol.project_id = %(project_id)s AND 
                        p.process_summary = d.project_cd 
                    ) a
                ) 
                ON CONFLICT (file_id, post_step) DO UPDATE SET post_results = 0
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
                count(f.file_name) as no_images,
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
              count(file_name) as no_images,
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
              count(file_name) as no_images,
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
