#!/usr/bin/env python3
#
# Script to update the Osprey statistics
# https://github.com/Smithsonian/Osprey
#
#
############################################
# Import modules
############################################
import logging
import logging.handlers
from logging.handlers import RotatingFileHandler
import time
from subprocess import run
import random
import sys

# For Postgres
import psycopg2
import psycopg2.extras

import edan

# Import settings from settings.py file
import settings

ver = "0.1"

############################################
# Logging
############################################
log_folder = "logs"

if not os.path.exists(log_folder):
    os.makedirs(log_folder)
current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
logfile_folder = '{log_folder}/{curtime}'.format(log_folder=log_folder, curtime=current_time)
if not os.path.exists(logfile_folder):
    os.makedirs(logfile_folder)
logfile = '{logfile_folder}/osprey.log'.format(logfile_folder=logfile_folder)
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M:%S',
                    handlers=[RotatingFileHandler(logfile, maxBytes=10000000,
                                                  backupCount=100)])
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logger = logging.getLogger("osprey")
logging.getLogger('osprey').addHandler(console)
logger.setLevel(logging.DEBUG)
logger.info("osprey version {}".format(ver))


############################################
# Functions
############################################

def query_database(query, parameters="", logging=None):
    try:
        conn = psycopg2.connect(host=settings.db_host,
                                database=settings.db_db,
                                user=settings.db_user,
                                password=settings.db_password)
    except psycopg2.Error as e:
        logging.error(e)
        raise InvalidUsage('System error', status_code=500)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    logging.info("parameters: {}".format(parameters))
    logging.info("query: {}".format(query))
    # Run query
    try:
        cur.execute(query, parameters)
        logging.info("cur.query: {}".format(cur.query.decode("utf-8")))
    except:
        logging.error("cur.query: {}".format(cur.query.decode("utf-8")))
    logging.info(cur.rowcount)
    if cur.rowcount == -1:
        data = None
    else:
        data = cur.fetchall()
    cur.close()
    conn.close()
    return data



def query_database2(query, parameters="", logging=None):
    try:
        conn = psycopg2.connect(host=settings.db_host,
                                database=settings.db_db,
                                user=settings.db_user,
                                password=settings.db_password)
    except psycopg2.Error as e:
        logging.error(e)
        raise InvalidUsage('System error', status_code=500)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    logging.info("parameters: {}".format(parameters))
    logging.info("query: {}".format(query))
    # Run query
    try:
        cur.execute(query, parameters)
        logging.info("cur.query: {}".format(cur.query.decode("utf-8")))
    except:
        logging.error("cur.query: {}".format(cur.query.decode("utf-8")))
    cur.close()
    conn.close()
    return




############################################
# Main
############################################
def main():
    # Get ongoing projects
    projects = query_database("SELECT * FROM projects WHERE project_status = 'Ongoing' and skip_project is not True", logging=logging)
    logger.debug(db_cursor.query.decode("utf-8"))
    # Loop each project
    for project in projects:
        logger.debug('project: {}'.format(project['project_title']))
        # total stats
        up_1 = query_database2(
                    """with dams_images as (
                        SELECT
                            media_file_name,
                            regexp_replace(
                                split_part(vfcu_pickup_loc, '-', 3)
                                , '\\D', '', 'g') as vfcu_pickup_loc
                        FROM
                            dams_vfcu_file_view_dpo
                        where
                            media_file_name ilike '%%.tif'
                            AND
                            project_cd = %(process_summary)s)
                    dams_objects
                    AS(
                        SELECT
                            media_file_name,
                            regexp_replace(
                            split_part(vfcu_pickup_loc, '-', 3)
                                , '\\D', '', 'g') as vfcu_pickup_loc
                        FROM
                            dams_vfcu_file_view_dpo
                        where
                            media_file_name like '%%.tif'
                            AND
                            project_cd = %(process_summary)s),
                    images as (
                        SELECT
                            count(distinct media_file_name) as images
                        FROM 
                            dams_images
                          ),
                            objects as (
                        SELECT
                            count(distinct media_file_name) as objects
                        FROM 
                            dams_objects
                          )
                      update
                        projects_stats
                        SET 
                          objects_digitized = objects.objects::int,
                          images_taken = images.images::int,
                          updated_at = NOW()
                        FROM
                        images, objects
                        WHERE project_id = %(project_id)s)
                            """)




        #Daily stats
        ,
        data_i as (
                      SELECT
                      media_file_name,
                      max(to_date(left(regexp_replace(vfcu_pickup_loc, '\\D', '', 'g'), 8), 'YYYYMMDD')) as filedate
        FROM
        dams_images
        GROUP
        BY
        media_file_name
        ),
        data_o as (
                      SELECT
                      media_file_name,
                      max(to_date(left(regexp_replace(vfcu_pickup_loc, '\\D', '', 'g'), 8), 'YYYYMMDD')) as filedate
        FROM
        dams_objects
        GROUP
        BY
        media_file_name
        ),
        data_ii as (
            SELECT
            count(media_file_name) as no_images,
                                      filedate
        FROM
        data_i
        group
        by
        filedate
        ),
        data_oo as (
            SELECT
            count(media_file_name) as no_objects,
                                      filedate
        FROM
        data_o
        group
        by
        filedate
        ),
        dateseries
        AS(
            SELECT
        date_trunc('day', dd)::date as date
        FROM
        generate_series
        ((select min(filedate)
        FROM
        data_ii)::timestamp
        , (select max(filedate)
        FROM
        data_ii)::timestamp
        , '1 day'::interval) dd
        )
        insert
        into
        projects_stats_detail
        (project_cd, project_id, time_interval, date, objects_digitized, images_captured)
        (
            SELECT
            '", project_cd, "',
            ", project_id, ",
            'daily',
            ds.date,
            coalesce(data_oo.no_objects, 0),
        coalesce(data_ii.no_images, 0)
        FROM
        dateseries
        ds
        LEFT
        JOIN
        data_ii
        ON(ds.date = data_ii.filedate) LEFT
        JOIN
        data_oo
        ON(ds.date = data_oo.filedate)
        );


        # weekly----
        stats_query < - paste0(file_select_subq, "
                               ,
                               data_i as (
                                             SELECT
                                             media_file_name,
                                             DATE_TRUNC('week', max(to_date(left(regexp_replace(vfcu_pickup_loc, '\\D', '', 'g'), 8), 'YYYYMMDD')))::date as filedate
        FROM
        dams_images
        GROUP
        BY
        media_file_name
        ),
        data_o as (
                      SELECT
                      media_file_name,
                      DATE_TRUNC('week', max(to_date(left(regexp_replace(vfcu_pickup_loc, '\\D', '', 'g'), 8), 'YYYYMMDD')))::date as filedate
        FROM
        dams_objects
        GROUP
        BY
        media_file_name
        ),
        data_ii as (
            SELECT
            count(media_file_name) as no_images,
                                      filedate
        FROM
        data_i
        group
        by
        filedate
        ),
        data_oo as (
            SELECT
            count(media_file_name) as no_objects,
                                      filedate
        FROM
        data_o
        group
        by
        filedate
        ),
        dateseries
        AS(
            SELECT
        distinct(date_trunc('week', dd)::date) as date
        FROM
        generate_series
        ((select min(filedate)
        FROM
        data_ii)::timestamp
        , (select max(filedate)
        FROM
        data_ii)::timestamp
        , '1 day'::interval) dd
        )
        insert
        into
        projects_stats_detail
        (project_cd, project_id, time_interval, date, objects_digitized, images_captured)
            (
            SELECT
        '", project_cd, "',
        ", project_id, ",
        'weekly',
        ds.date,
        coalesce(data_oo.no_objects, 0),
        coalesce(data_ii.no_images, 0)
        FROM
        dateseries
        ds
        LEFT
        JOIN
        data_oo
        ON(ds.date = data_oo.filedate) LEFT
        JOIN
        data_ii
        ON(ds.date = data_ii.filedate)
        )")

        mdpp_data < - dbGetQuery(db, stats_query)

        # monthly----
        stats_query < - paste0(file_select_subq, "
                               ,

                               data_i as (
                                             SELECT
                                             media_file_name,
                                             DATE_TRUNC('month', max(to_date(left(regexp_replace(vfcu_pickup_loc, '\\D', '', 'g'), 8), 'YYYYMMDD')))::date as filedate
        FROM
        dams_images
        GROUP
        BY
        media_file_name
        ),
        data_o as (
                      SELECT
                      media_file_name,
                      DATE_TRUNC('month', max(to_date(left(regexp_replace(vfcu_pickup_loc, '\\D', '', 'g'), 8), 'YYYYMMDD')))::date as filedate
        FROM
        dams_objects
        GROUP
        BY
        media_file_name
        ),
        data_ii as (
            SELECT
            count(media_file_name) as no_images,
                                      filedate
        FROM
        data_i
        group
        by
        filedate
        ),
        data_oo as (
            SELECT
            count(media_file_name) as no_objects,
                                      filedate
        FROM
        data_o
        group
        by
        filedate
        ),
        dateseries
        AS(
            SELECT
        distinct(date_trunc('month', dd)::date) as date
        FROM
        generate_series
        ((select min(filedate)
        FROM
        data_i)::timestamp
        , (select max(filedate)
        FROM
        data_i)::timestamp
        , '1 day'::interval) dd
        )
        insert
        into
        projects_stats_detail
        (project_cd, project_id, time_interval, date, objects_digitized, images_captured)
            (
            SELECT
        '", project_cd, "',
        ", project_id, ",
        'monthly',
        ds.date,
        coalesce(data_oo.no_objects, 0),
        coalesce(data_ii.no_images, 0)
        FROM
        dateseries
        ds
        LEFT
        JOIN
        data_oo
        ON(ds.date = data_oo.filedate) LEFT
        JOIN
        data_ii
        ON(ds.date = data_ii.filedate)
        )")

        # Update DAMS UAN
        n < - dbSendQuery(db, paste0("
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
        dams_cdis_file_status_view_dpo
        d,
        files
        f
        WHERE
        d.project_cd = '", project_cd, "' and
                       d.file_name = f.file_name) d
        WHERE
        f.file_id = d.file_id;
        "))





        #Preview to IDS, wont work with some, including NMNH
        # might need to do this via edan only

        update
        files
        set
        preview_image = ('https://ids.si.edu/ids/deliveryService?id=' | | dams_uan)
        where
        dams_uan is not null
        AND
        preview_image
        IS
        NULL and folder_id in (select folder_id from folders WHERE project_id= 133);


        #Link to IIIF viewer
        insert
        into
        files_links(
            file_id,
            link_name,
            link_url
        )
            (
            select
        f.file_id,
        'IIIF Manifest',
        'https://ids.si.edu/ids/manifest/' | | f.dams_uan
        from files f
        where
        f.dams_uan is not null
        AND
        f.file_id
        NOT
        IN(
            SELECT
        file_id
        FROM
        files_links
        WHERE
        link_name = 'IIIF Manifest'
        )
        and folder_id in (select folder_id from folders WHERE project_id= 133)
        );


        # Link to IIIF manifest
        insert
        into
        files_links(
            file_id,
            link_name,
            link_url
        )
            (
            select
        file_id,
        '<img src="/static/logo-iiif.png">',
        'https://iiif.si.edu/mirador/?manifest=https://ids.si.edu/ids/manifest/' | | dams_uan
        from files f
        where
        f.dams_uan is not null
        AND
        f.file_id
        NOT
        IN(
            SELECT
        file_id
        FROM
        files_links
        WHERE
        link_name = '<img src="/static/logo-iiif.png">'
        )
        and folder_id in (select folder_id from folders WHERE project_id= 133)
        );



        # Link to NMNH ARK From mongo
        insert
        into
        files_links(
            file_id,
            link_name,
            link_url
        )
            (
            select
        file_id,
        'Collection Database',
        'https://iiif.si.edu/mirador/?manifest=https://ids.si.edu/ids/manifest/' | | dams_uan
        from files f
        where
        f.dams_uan is not null
        AND
        f.file_id
        NOT
        IN(
            SELECT
        file_id
        FROM
        files_links
        WHERE
        link_name = 'Collection Database'
        )
        and folder_id in (select folder_id from folders WHERE project_id= 133)
        );



        --Check if the file is in the DAMS view dams_vfcu_file_view_dpo
        UPDATE
        file_postprocessing
        SET
        post_results = 0
        WHERE
        post_step = 'in_dams'
        AND
        file_id in
        (
            SELECT
            file_id
            FROM
            (
            SELECT
            f.file_id
            FROM
            dams_vfcu_file_view_dpo d,
            files f
            WHERE
            d.project_cd = 'sg_aspace' and
            d.media_file_name = f.file_name || '.tif' AND
            f.folder_id = 1358)
        a
        );

        -- insert
        INSERT INTO file_postprocessing
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
            files f
            WHERE
            d.project_cd = 'sg_aspace' and
            d.media_file_name = f.file_name || '.tif' AND
            f.folder_id = 1358) a
        );



        --Set folder as delivered
        UPDATE
        folders
        SET
        delivered_to_dams = 1
        WHERE
        folder_id = 1845;




        # Generate list of folders in the path
        folders = query_database("SELECT * FROM folders WHERE project_id = %(project_id)s", {'project_id': project['project_id']})
        # Check each folder
        for folder in folders:
            files = query_database("SELECT * FROM files WHERE folder_id = %(folder_id)s", {'folder_id': folder['folder_id']})
            for file in files:
                results = edan.searchEDAN(file['file_name'], settings.AppID, settings.AppKey)
    return


############################################
# Main loop
############################################
if __name__ == "__main__":
    if run_debug == 'debug':
        main()
    else:
        while True:
            try:
                # Check if there is a pre script to run
                if settings.pre_script is not None:
                    p = subprocess.Popen([settings.pre_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    (out, err) = p.communicate()
                    if p.returncode != 0:
                        print("Pre-script error")
                        print(out)
                        print(err)
                        sys.exit(9)
                    else:
                        print(out)
                # Run main function
                mainval = main()
                # Check if there is a post script to run
                if settings.post_script is not None:
                    p = subprocess.Popen([settings.post_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    (out, err) = p.communicate()
                    if p.returncode != 0:
                        print("Post-script error")
                        print(out)
                        print(err)
                        sys.exit(9)
                    else:
                        print(out)
                if settings.sleep is None:
                    logger.info("Process completed!")
                    compress_log()
                    sys.exit(0)
                else:
                    logger.info("Sleeping for {} secs".format(settings.sleep))
                    # Sleep before trying again
                    time.sleep(settings.sleep)
                    continue
            except KeyboardInterrupt:
                # print("Ctrl-c detected. Leaving program.")
                logger.info("Ctrl-c detected. Leaving program.")
                try:
                    if 'folder_id' in globals():
                        conn2 = psycopg2.connect(host=settings.db_host, database=settings.db_db, user=settings.db_user,
                                                 password=settings.db_password, connect_timeout=60)
                        conn2.autocommit = True
                        db_cursor2 = conn2.cursor()
                        db_cursor2.execute("UPDATE folders SET processing = 'f' WHERE folder_id = %(folder_id)s",
                                           {'folder_id': folder_id})
                        conn2.close()
                except Exception as e:
                    print("Error: {}".format(e))
                # Compress logs
                compress_log()
                sys.exit(0)
            except Exception as e:
                logger.error("There was an error: {}".format(e))
                try:
                    if 'folder_id' in globals():
                        conn2 = psycopg2.connect(host=settings.db_host, database=settings.db_db, user=settings.db_user,
                                                 password=settings.db_password, connect_timeout=60)
                        conn2.autocommit = True
                        db_cursor2 = conn2.cursor()
                        db_cursor2.execute("UPDATE folders SET processing = 'f' WHERE folder_id = %(folder_id)s",
                                           {'folder_id': folder_id})
                        conn2.close()
                except Exception as e:
                    print("Error: {}".format(e))
                # Compress logs
                compress_log()
                sys.exit(1)


sys.exit(0)
