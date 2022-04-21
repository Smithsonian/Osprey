#!/usr/bin/env python3
#
# Osprey script
# https://github.com/Smithsonian/Osprey
#
# Validate images from a vendor
#
############################################
# Import modules
############################################
import logging
import logging.handlers
import time
from subprocess import run
import random

# For Postgres
import psycopg2

# Import settings from settings.py file
import settings

# Import helper functions
from functions import *

# Import queries from queries.py file
import queries

# Set current dir
filecheck_dir = os.getcwd()

ver = "1.0.1"

############################################
# Logging
############################################
if settings.log_folder is None:
    # Use current directory
    log_folder = "{}/logs".format(filecheck_dir)
else:
    log_folder = settings.log_folder

if not os.path.exists(log_folder):
    os.makedirs(log_folder)
current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
logfile_name = 'osprey.log'
logfile_folder = '{log_folder}/{curtime}'.format(log_folder=log_folder, curtime=current_time)
if not os.path.exists(logfile_folder):
    os.makedirs(logfile_folder)
logfile = '{logfile_folder}/{logfile_name}'.format(logfile_folder=logfile_folder, logfile_name=logfile_name)


# Rotate
# Set up a specific logger with our desired output level
logger = logging.getLogger('osprey')
logger.setLevel(logging.DEBUG)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('osprey').addHandler(console)

# Add the log message handler to the logger
handler = logging.handlers.RotatingFileHandler(logfile, maxBytes=1000000, backupCount=100)
logger.addHandler(handler)

logger.info("osprey version {}".format(ver))


############################################
# Check requirements
############################################
if check_requirements(settings.jhove_path) is False:
    logger.error("JHOVE was not found")
    sys.exit(1)

if check_requirements('identify') is False:
    logger.error("Imagemagick was not found")
    sys.exit(1)

if check_requirements('exiftool') is False:
    logger.error("exiftool was not found")
    sys.exit(1)


############################################
# Main
############################################
def main():
    # Check that the paths are valid dirs and are mounted
    for p_path in settings.project_paths:
        if not os.path.isdir(p_path):
            logger.error("Path not found: {}".format(p_path))
            continue
    # Connect to the database
    logger.debug("Connecting to database")
    try:
        conn = psycopg2.connect(host=settings.db_host, database=settings.db_db, user=settings.db_user,
                                password=settings.db_password, connect_timeout=60)
        conn.autocommit = True
        db_cursor = conn.cursor()
    except psycopg2.Error as e:
        logger.error("Database error: {}".format(e))
        sys.exit(1)
    # Clear project shares
    db_cursor.execute(queries.remove_shares, {'project_id': settings.project_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    # Check project shares
    for share in settings.project_shares:
        logger.info("Share: {} ({})".format(share[0], share[1]))
        share_disk = shutil.disk_usage(share[0])
        try:
            share_percent = round(share_disk.used / share_disk.total, 4) * 100
            db_cursor.execute(queries.update_share,
                              {'project_id': settings.project_id, 'share': share[1], 'localpath': share[0],
                               'used': share_percent, 'total': share_disk.total})
            logger.debug(db_cursor.query.decode("utf-8"))
        except Exception as e:
            logger.error("Error checking the share {} ({})".format(share[0], e))
            continue
    # Update project
    db_cursor.execute(queries.update_projectchecks, {'project_file_checks': ','.join(settings.project_file_checks),
                                                     'project_id': settings.project_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    # Loop each project path
    for project_path in settings.project_paths:
        logger.debug('project_path: {}'.format(project_path))
        # Generate list of folders in the path
        folders = []
        for entry in os.scandir(project_path):
            if entry.is_dir():
                folders.append(entry.path)
            else:
                logger.error("Extraneous files in: {}".format(entry.path))
                logger.info("Leaving program")
                sys.exit(1)
        # No folders found
        if len(folders) == 0:
            logger.info("No folders found in: {}".format(project_path))
            continue
        # Shuffle folders
        random.shuffle(folders)
        # Check each folder
        for folder in folders:
            run_checks_folder(settings.project_id, folder, db_cursor, logger)
    # Disconnect from db
    conn.close()
    if settings.sleep is False:
        logger.info("Process completed!")
        compress_log(filecheck_dir, logfile_folder)
        sys.exit(0)
    else:
        logger.info("Sleeping for {} secs".format(settings.sleep))
        # Sleep before trying again
        time.sleep(settings.sleep)
        return None


############################################
# Main loop
############################################
if __name__ == "__main__":
    # main()
    while True:
        try:
            # Check if there is a pre script to run
            if settings.pre_script is not None:
                run([settings.pre_script], check=True)
            # Run main function
            main()
            # Check if there is a post script to run
            if settings.post_script is not None:
                run([settings.post_script], check=True)
        except KeyboardInterrupt:
            # print("Ctrl-c detected. Leaving program.")
            logger.info("Ctrl-c detected. Leaving program.")
            # Compress logs
            compress_log(filecheck_dir, logfile_folder)
            sys.exit(0)
        except Exception as e:
            logger.error("There was an error: {}".format(e))
            # Compress logs
            compress_log(filecheck_dir, logfile_folder)
            sys.exit(1)


sys.exit(0)
