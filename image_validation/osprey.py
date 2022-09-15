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
from logging.handlers import RotatingFileHandler
import time
from subprocess import run
import random
import sys

# For Postgres
import psycopg2

# Import settings from settings.py file
import settings

# Import helper functions
from functions import *

# Import queries from queries.py file
import queries

ver = "1.1.3"

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


# Pass an argument in the CLI 'debug'
if len(sys.argv) > 1:
    run_debug = sys.argv[1]
else:
    run_debug = False


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
    # db_cursor.execute(queries.remove_shares, {'project_id': settings.project_id})
    # logger.debug(db_cursor.query.decode("utf-8"))
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
            # run_checks_folder_p(settings.project_id, folder, logfile_folder, db_cursor, logger)
    # Disconnect from db
    conn.close()
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
                        logger.info("folder_id in globals: {}".format(folder_id))
                        conn2 = psycopg2.connect(host=settings.db_host, database=settings.db_db, user=settings.db_user,
                                                 password=settings.db_password, connect_timeout=60)
                        conn2.autocommit = True
                        db_cursor2 = conn2.cursor()
                        db_cursor2.execute("UPDATE folders SET processing = 'f' WHERE folder_id = %(folder_id)s",
                                           {'folder_id': folder_id})
                        conn2.close()
                except Exception as e:
                    logging.error("Error: {}".format(e))
                # Compress logs
                compress_log()
                sys.exit(0)
            except Exception as e:
                logger.error("There was an error: {}".format(e))
                try:
                    if 'folder_id' in globals():
                        logger.info("folder_id in globals: {}".format(folder_id))
                        conn2 = psycopg2.connect(host=settings.db_host, database=settings.db_db, user=settings.db_user,
                                                 password=settings.db_password, connect_timeout=60)
                        conn2.autocommit = True
                        db_cursor2 = conn2.cursor()
                        db_cursor2.execute("UPDATE folders SET processing = 'f' WHERE folder_id = %(folder_id)s",
                                           {'folder_id': folder_id})
                        conn2.close()
                except Exception as e:
                    logging.error("Error: {}".format(e))
                # Compress logs
                compress_log()
                sys.exit(1)


sys.exit(0)
