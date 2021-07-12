#!/usr/bin/env python3
#
# Osprey script
# https://github.com/Smithsonian/Osprey
#
# Validate sound files from a vendor
# CURRENTLY BROKEN, needs work
#
############################################
# Import modules
############################################
import locale
import logging
import random
import time
from time import localtime, strftime
# For Postgres
import psycopg2
# Import settings from settings.py file
import settings
# Import helper functions
from functions import *

# Import queries from queries.py file
import queries

# Save current directory
filecheck_dir = os.getcwd()

ver = "0.8.0"

# Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')

############################################
# Check requirements
############################################
if check_requirements(settings.jhove_path) is False:
    print("JHOVE was not found")
    sys.exit(1)

if check_requirements('soxi') is False:
    print("SoX was not found")
    sys.exit(1)

############################################
# Logging
############################################
if not os.path.exists('{}/logs'.format(filecheck_dir)):
    os.makedirs('{}/logs'.format(filecheck_dir))
current_time = strftime("%Y%m%d%H%M%S", localtime())
logfile_name = '{}.log'.format(current_time)
logfile = '{filecheck_dir}/logs/{logfile_name}'.format(filecheck_dir=filecheck_dir, logfile_name=logfile_name)
# from http://stackoverflow.com/a/9321890
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M:%S',
                    filename=logfile,
                    filemode='a')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logger = logging.getLogger("osprey")
logging.getLogger('osprey').addHandler(console)
logger.info("osprey version {}".format(ver))


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
    logger.info("Connecting to database")
    conn = psycopg2.connect(host=settings.db_host, database=settings.db_db, user=settings.db_user, connect_timeout=60)
    conn.autocommit = True
    db_cursor = conn.cursor()
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
            logger.error("Error checking the share {} ({e})".format(share[0], e))
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
        # No folders found
        if len(folders) == 0:
            continue
        # Randomize folders
        random.shuffle(folders)
        # Run each folder
        for folder in folders:
            folder_path = folder
            logger.info(folder_path)
            folder_name = os.path.basename(folder)
            # Check if the folder exists in the database
            global folder_id
            folder_id = check_folder(folder_name, folder_path, settings.project_id, db_cursor)
            if folder_id is None:
                logger.error("Folder {} had an error".format(folder_name))
                continue
            # Check if folder is ready or in dams
            db_cursor.execute(queries.folder_in_dams, {'folder_id': folder_id})
            logger.debug(db_cursor.query.decode("utf-8"))
            f_in_dams = db_cursor.fetchone()
            if f_in_dams[0] == 0 or f_in_dams[0] == 1:
                # Folder ready for dams or in dams already, skip
                logger.info("Folder in DAMS, skipping {}".format(folder_path))
                continue
            # Check if another computer is processing the folder
            db_cursor.execute(queries.folder_check_processing, {'folder_id': folder_id})
            logger.debug(db_cursor.query.decode("utf-8"))
            folder_proc = db_cursor.fetchone()
            if folder_proc[0]:
                # In case process is stuck or crashed, reset setting if its been more than 2 days
                if folder_proc[1] / (60 * 60 * 24) < 2.0:
                    logger.info("Folder checked by another computer, going for the next one {}".format(folder_path))
                    continue
            # Set as processing
            db_cursor.execute(queries.folder_processing_update, {'folder_id': folder_id, 'processing': 't'})
            logger.debug(db_cursor.query.decode("utf-8"))
            os.chdir(folder_path)
            files = glob.glob("*.wav")
            random.shuffle(files)
            logger.debug("Files in {}: {}".format(folder_path, ','.join(files)))
            logger.info("{} files in {}".format(len(files), folder_path, ))
            # Remove files to ignore
            if settings.ignore_string is not None:
                files = [x for x in files if settings.ignore_string not in x]
                logger.debug("Files without ignored strings in {}: {}".format(folder_path, ','.join(files)))
            ###########################
            # WAV files
            ###########################
            if settings.project_type == 'wav':
                # Check each wav file
                for file in files:
                    logger.info("Running checks on file {}".format(file))
                    process_wav(file, folder_path, folder_id, db_cursor, logger)
                # MD5
                if len(glob.glob1("*.md5")) == 1:
                    db_cursor.execute(queries.update_folders_md5, {'folder_id': folder_id, 'filetype': 'wav', 'md5': 0})
                    logger.debug(db_cursor.query.decode("utf-8"))
                # Check for deleted files
                if settings.check_deleted:
                    check_deleted('wav', db_cursor, logger)
            ###########################
            # TIF Files
            ###########################
            elif settings.project_type == 'tif':
                if (os.path.isdir(folder_path + "/" + settings.raw_files_path) is False and os.path.isdir(
                        folder_path + "/" + settings.tif_files_path) is False):
                    logger.info("Missing TIF and RAW folders")
                    db_cursor.execute(queries.update_folder_status9,
                                      {'error_info': "Missing TIF and RAW folders", 'folder_id': folder_id})
                    logger.debug(db_cursor.query.decode("utf-8"))
                    delete_folder_files(folder_id, db_cursor, logger)
                    continue
                elif os.path.isdir(folder_path + "/" + settings.tif_files_path) is False:
                    logger.info("Missing TIF folder")
                    db_cursor.execute(queries.update_folder_status9,
                                      {'error_info': "Missing TIF folder", 'folder_id': folder_id})
                    logger.debug(db_cursor.query.decode("utf-8"))
                    delete_folder_files(folder_id, db_cursor, logger)
                    continue
                elif os.path.isdir(folder_path + "/" + settings.raw_files_path) is False:
                    logger.info("Missing RAW folder")
                    db_cursor.execute(queries.update_folder_status9,
                                      {'error_info': "Missing RAW folder", 'folder_id': folder_id})
                    logger.debug(db_cursor.query.decode("utf-8"))
                    delete_folder_files(folder_id, db_cursor, logger)
                    continue
                else:
                    logger.info("Both folders present")
                    db_cursor.execute(queries.update_folder_0, {'folder_id': folder_id})
                    logger.debug(db_cursor.query.decode("utf-8"))
                    folder_full_path = "{}/{}".format(folder_path, settings.tif_files_path)
                    os.chdir(folder_full_path)
                    files = glob.glob("*.tif")
                    logger.info(files)
                    # Remove temp files
                    if settings.ignore_string is not None:
                        files = [x for x in files if settings.ignore_string not in x]
                        logger.debug("Files without ignored strings in {}: {}".format(folder_path, ','.join(files)))
                    for file in files:
                        logger.info("Running checks on file {}".format(file))
                        process_tif(file, folder_path, folder_id, folder_full_path, db_cursor, logger)
                    # MD5
                    if len(glob.glob(folder_path + "/" + settings.tif_files_path + "/*.md5")) == 1:
                        db_cursor.execute(queries.update_folders_md5,
                                          {'folder_id': folder_id, 'filetype': 'tif', 'md5': 0})
                        logger.debug(db_cursor.query.decode("utf-8"))
                    else:
                        db_cursor.execute(queries.update_folders_md5,
                                          {'folder_id': folder_id, 'filetype': 'tif', 'md5': 1})
                        logger.debug(db_cursor.query.decode("utf-8"))
                    if len(glob.glob(folder_path + "/" + settings.raw_files_path + "/*.md5")) == 1:
                        db_cursor.execute(queries.update_folders_md5,
                                          {'folder_id': folder_id, 'filetype': 'raw', 'md5': 0})
                        logger.debug(db_cursor.query.decode("utf-8"))
                    else:
                        db_cursor.execute(queries.update_folders_md5,
                                          {'folder_id': folder_id, 'filetype': 'raw', 'md5': 1})
                        logger.debug(db_cursor.query.decode("utf-8"))
                # Check for deleted files
                if settings.check_deleted:
                    check_deleted('tif', db_cursor, logger)
            folder_updated_at(folder_id, db_cursor, logger)
            # Update folder stats
            update_folder_stats(folder_id, db_cursor, logger)
            # Set as processing done
            db_cursor.execute(queries.folder_processing_update, {'folder_id': folder_id, 'processing': 'f'})
            logger.debug(db_cursor.query.decode("utf-8"))
    os.chdir(filecheck_dir)
    # Disconnect from db
    conn.close()
    logger.info("Sleeping for {} secs".format(settings.sleep))
    # Sleep before trying again
    time.sleep(settings.sleep)


############################################
# Main loop
############################################
if __name__ == "__main__":
    while True:
        # main()
        try:
            main()
        except KeyboardInterrupt:
            print("Ctrl-c detected. Leaving program.")
            try:
                conn2 = psycopg2.connect(host=settings.db_host, database=settings.db_db, user=settings.db_user,
                                         connect_timeout=60)
                conn2.autocommit = True
                db_cursor2 = conn2.cursor()
                db_cursor2.execute("UPDATE folders SET processing = 'f' WHERE folder_id = %(folder_id)s",
                                   {'folder_id': folder_id})
                conn2.close()
            except psycopg2.Error as e:
                print(e.pgerror)
            # Compress logs
            compress_log(filecheck_dir)
            sys.exit(0)
        except Exception as e:
            print("There was an error: {}".format(e))
            try:
                conn2 = psycopg2.connect(host=settings.db_host, database=settings.db_db, user=settings.db_user,
                                         connect_timeout=60)
                conn2.autocommit = True
                db_cursor2 = conn2.cursor()
                db_cursor2.execute("UPDATE folders SET processing = 'f' WHERE folder_id = %(folder_id)s",
                                   {'folder_id': folder_id})
                conn2.close()
            except psycopg2.Error as e:
                print(e.pgerror)
            # Compress logs
            compress_log(filecheck_dir)
            sys.exit(1)

sys.exit(0)
