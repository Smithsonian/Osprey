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
try:
    cur.execute("""
        with dimages as (SELECT
              f.file_name,
              fol.date
              fROM
              files f,
              folders fol
              where
              f.folder_id = fol.folder_id and
                dams_uan is not null
                and fol.project_id = %(project_id)s),
      images as (SELECT
                    f.file_name,
                    fol.date
                    fROM
                    files f,
                    folders fol
                    where
                    f.folder_id = fol.folder_id and
                    fol.project_id = %(project_id)s),
            project_objects AS (SELECT
                          f.file_name,
                          fol.date
                          fROM
                          files f,
                          folders fol
                          where
                          f.folder_id = fol.folder_id and
                            fol.project_id = %(project_id)s),
            dams_images as (
        SELECT
            count(distinct file_name) as images
        FROM
            dimages
          ),
          objects as (
      SELECT
          count(distinct file_name) as objects
      FROM
          project_objects
        ),
        images_captured as (
    SELECT
        count(distinct file_name) as images
    FROM
        images
      )
      update
        projects_stats
        SET
          objects_digitized = objects.objects::int,
          images_public = dams_images.images::int,
          images_taken = images_captured.images::int,
          updated_at = NOW()
        FROM
        images_captured, objects, dams_images
        WHERE project_id = %(project_id)s        
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))


# clear stats
try:
    cur.execute("""
       delete from projects_stats_detail 
        WHERE project_id = %(project_id)s        
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))


# daily
try:
    cur.execute("""
             with dams_images as (
    SELECT
          f.file_name,
          max(fol.date) as date
    FROM
          files f,
          folders fol
    WHERE
          f.folder_id = fol.folder_id and
          dams_uan is not null and
          fol.project_id = %(project_id)s
    GROUP BY f.file_name
        ),
        di as (
          SELECT
              count(file_name) as no_images,
              date
          FROM
              dams_images
              group by date
        ),
    dateseries AS (
        SELECT date_trunc('day', dd)::date as date
          FROM generate_series
                  ( (select min(date) FROM di)::timestamp
                  , (select max(date) FROM di)::timestamp
                  , '1 day'::interval) dd
        )

      insert into
        projects_stats_detail
        (project_id, time_interval, date, objects_digitized, images_captured)
        (
        SELECT
          %(project_id)s,
          'daily',
          ds.date,
          coalesce(di.no_images, 0),
          coalesce(di.no_images, 0)
      FROM
        dateseries ds LEFT JOIN di ON (ds.date = di.date)
      )        
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))



# weekly
try:
    cur.execute("""
  with dams_images as (
    SELECT
          f.file_name,
          max(fol.date) as date
    FROM
          files f,
          folders fol
    WHERE
          f.folder_id = fol.folder_id and
          dams_uan is not null and
          fol.project_id = %(project_id)s
    GROUP BY f.file_name
        ),
        di as (
          SELECT
              count(file_name) as no_images,
              date_trunc('week', date)::date as date
          FROM
              dams_images
              group by date
        ),
    dateseries AS (
        SELECT distinct(date_trunc('week', dd)::date) as date
          FROM generate_series
                  ( (select min(date) FROM di)::timestamp
                  , (select max(date) FROM di)::timestamp
                  , '1 day'::interval) dd
        )

      insert into
        projects_stats_detail
        (project_id, time_interval, date, objects_digitized, images_captured)
        (
        SELECT
          %(project_id)s,
          'weekly',
          ds.date,
          coalesce(di.no_images, 0),
          coalesce(di.no_images, 0)
      FROM
        dateseries ds LEFT JOIN di ON (ds.date = di.date)
      )  
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))




# monthly
try:
    cur.execute("""
            with dams_images as (
    SELECT
          f.file_name,
          date_trunc('month', max(fol.date))::date as date
    FROM
          files f,
          folders fol
    WHERE
          f.folder_id = fol.folder_id and
          dams_uan is not null and
          fol.project_id = %(project_id)s
    GROUP BY f.file_name
        ),
        di as (
          SELECT
              count(*) as no_images,
              date
          FROM
              dams_images
              group by date
        ),
    dateseries AS (
        SELECT distinct(date_trunc('month', dd)::date) as date
          FROM generate_series
                  ( (select min(date) FROM di)::timestamp
                  , (select max(date) FROM di)::timestamp
                  , '1 day'::interval) dd
        )

      insert into
        projects_stats_detail
        (project_id, time_interval, date, objects_digitized, images_captured)
        (
        SELECT
          %(project_id)s,
          'monthly',
          ds.date,
          coalesce(di.no_images, 0),
          coalesce(di.no_images, 0)
      FROM
        dateseries ds LEFT JOIN di ON (ds.date = di.date)
      )
        """, {'project_id': project_id})
except Exception as error:
    print("Error: {}".format(error))



cur.close()
conn.close()

sys.exit(0)
