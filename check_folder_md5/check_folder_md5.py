#!/usr/bin/env python3
#
# check_folder_md5 script 
#
# Checks that subfolders with md5 files to match the md5 hashes with the files
#
############################################
# Import modules
############################################
import glob
import locale
import logging
import os
import shutil
import subprocess
import sys
from time import localtime, strftime

# For Postgres
import psycopg2

# Import queries from queries.py file
import queries

# Import settings from settings.py file
import settings


ver = "0.1.2"

# Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')


# Save current directory
filecheck_dir = os.getcwd()

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
# logging.getLogger('').addHandler(console)
logger1 = logging.getLogger("check_md5")
logging.getLogger('check_md5').addHandler(console)
logger1.info("check_md5 version {}".format(ver))


############################################

def compress_log(filecheck_dir):
    """
    Compress log files
    """
    os.chdir('{}/logs'.format(filecheck_dir))
    for file in glob.glob('*.log'):
        subprocess.run(["zip", "{}.zip".format(file), file])
        os.remove(file)
    os.chdir(filecheck_dir)
    return True


def check_folder(folder_name, folder_path, project_id, db_cursor):
    """
    Check if a folder exists, add if it does not
    """
    db_cursor.execute(queries.select_folderid,
                      {'project_folder': folder_name, 'folder_path': folder_path, 'project_id': project_id})
    folder_id = db_cursor.fetchone()
    if folder_id is None:
        return None
    return folder_id[0]


def main():
    # Check that the paths are valid dirs and are mounted
    for p_path in settings.project_paths:
        if not os.path.isdir(p_path):
            logger1.error("Path not found: {}".format(p_path))
            continue
    # Connect to the database
    logger1.info("Connecting to database")
    conn = psycopg2.connect(host=settings.db_host, database=settings.db_db,
                            user=settings.db_user, password=settings.db_password, connect_timeout=60)
    conn.autocommit = True
    db_cursor = conn.cursor()
    # Loop each project path
    for project_path in settings.project_paths:
        logger1.debug('project_path: {}'.format(project_path))
        # Generate list of folders in the path
        folders = []
        for entry in os.scandir(project_path):
            if entry.is_dir():
                folders.append(entry.path)
        # No folders found
        if len(folders) == 0:
            continue
        # Run each folder
        for folder in folders:
            folder_path = folder
            logger1.info(folder_path)
            folder_name = os.path.basename(folder)
            # Check if the folder exists in the database
            global folder_id
            folder_id = check_folder(folder_name, folder_path, settings.project_id, db_cursor)
            if folder_id is None:
                logger1.error("Folder {} had an error".format(folder_name))
                continue
            # Check if folder is ready or in dams
            db_cursor.execute(queries.folder_in_dams, {'folder_id': folder_id})
            logger1.debug(db_cursor.query.decode("utf-8"))
            f_in_dams = db_cursor.fetchone()
            if f_in_dams[0] == 0:
                # Folder ready for dams, skip
                logger1.info("Folder ready for DAMS, skipping {}".format(folder_path))
                continue
            elif f_in_dams[0] == 1:
                # Folder in dams already, move to delete folder
                shutil.move(folder_path, settings.del_path)
                logger1.info("Folder in DAMS, moving to delete path {}".format(folder_path))
                continue
            # Check if another computer is processing the folder
            db_cursor.execute(queries.folder_check_processing, {'folder_id': folder_id})
            logger1.debug(db_cursor.query.decode("utf-8"))
            folder_proc = db_cursor.fetchone()
            if folder_proc[0] == True:
                logger1.info("Folder checked by another computer, going for the next one {}".format(folder_path))
                continue
            # Check if another computer is checking the md5 of the folder
            db_cursor.execute(queries.folder_check_processing_md5, {'folder_id': folder_id})
            logger1.debug(db_cursor.query.decode("utf-8"))
            folder_proc = db_cursor.fetchone()
            if folder_proc[0] == True:
                logger1.info("Folder MD5 checked by another computer, going for the next one {}".format(folder_path))
                continue
            # Check if the folder has been fully checked
            db_cursor.execute(queries.folder_check_filechecks, {'folder_id': folder_id})
            logger1.debug(db_cursor.query.decode("utf-8"))
            folder_proc = db_cursor.fetchone()
            if folder_proc[0] == 0:
                logger1.info("Folder empty {}".format(folder_path))
                continue
            if folder_proc[1] > 0:
                logger1.info("Folder not fully checked {}".format(folder_path))
                continue
            # Check if the folder has been tagged as OK
            db_cursor.execute(queries.folder_final_check, {'folder_id': folder_id})
            logger1.debug(db_cursor.query.decode("utf-8"))
            folder_proc = db_cursor.fetchone()
            if folder_proc[0] != 0:
                logger1.info("Folder not tagged as OK {}".format(folder_path))
                continue
            # Set as processing
            db_cursor.execute(queries.folder_processing_update, {'folder_id': folder_id, 'processing': 't'})
            logger1.debug(db_cursor.query.decode("utf-8"))
            # Check each subfolder
            checked_ok = 0
            for subfolder in settings.subfolders:
                if not os.path.isdir(folder_path + "/" + subfolder):
                    logger1.info("Missing subfolder: {}".format(subfolder))
                    continue
                else:
                    folder_full_path = "{}/{}".format(folder_path, subfolder)
                    # Run md5 script
                    # from https://github.com/Smithsonian/MassDigi-tools/tree/master/check_md5/cli
                    p = subprocess.Popen(['./check_md5.py', folder_full_path], stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
                    (out, err) = p.communicate()
                    if p.returncode == 0:
                        checked_ok += 1
                        logger1.info("Files match the md5 file: {}/{}".format(folder_name, subfolder))
                        logger1.debug("Results for {}/{}: {}".format(folder_name, subfolder, out))
                    else:
                        logger1.error("Folder did not pass: {}/{}".format(folder_name, subfolder))
                        err_msg = "Folder did not pass MD5 file check: {}/{}".format(folder_name, subfolder)
                        logger1.debug("Results for {}/{}: {}".format(folder_name, subfolder, out))
                        logger1.debug("Error msg for {}/{}: {}".format(folder_name, subfolder, err))
            if checked_ok == len(settings.subfolders):
                # Folders were checked and passed
                logger1.info("Folder passed: {}".format(folder_path))
                # Move folder to DAMS pickup
                # Check that it doesn't exist first
                if os.path.isdir("{}/{}".format(settings.move_to_path, folder_name)):
                    logger1.error("Folder exists in target {}".format(folder_path))
                    sys.exit(1)
                try:
                    shutil.move(folder_path, settings.move_to_path)
                except Exception as e:
                    logger1.error("Could not move folder {} - {}".format(folder_path, e))
                    sys.exit(1)
                # Update database
                db_cursor.execute(queries.file_postprocessing1, {'folder_id': folder_id})
                db_cursor.execute(queries.file_postprocessing2, {'folder_id': folder_id})
                db_cursor.execute(queries.file_postprocessing3, {'folder_id': folder_id})
                db_cursor.execute(queries.file_postprocessing4, {'folder_id': folder_id})
            else:
                # Something didn't pass
                logger1.error("Folder failed: {}".format(folder_path))
                db_cursor.execute(queries.folder_status, {'folder_id': folder_id, 'status': 2, 'error_info': err_msg})
            db_cursor.execute(queries.folder_processing_update, {'folder_id': folder_id, 'processing': 'f'})
            logger1.debug(db_cursor.query.decode("utf-8"))
    # Disconnect from db
    conn.close()
    return


############################################
# Main loop
############################################
if __name__ == "__main__":
    # main()
    try:
        main()
    except KeyboardInterrupt:
        print("Ctrl-c detected. Leaving program.")
        try:
            conn2 = psycopg2.connect(host=settings.db_host, database=settings.db_db,
                                     user=settings.db_user, password=settings.db_password,
                                     connect_timeout=60)
            conn2.autocommit = True
            db_cursor2 = conn2.cursor()
            db_cursor2.execute("UPDATE folders SET processing_md5 = 'f' WHERE folder_id = %(folder_id)s",
                               {'folder_id': folder_id})
            conn2.close()
        except Exception as e:
            print(e)
        # Compress logs
        compress_log(filecheck_dir)
        sys.exit(0)
    except Exception as e:
        print("There was an error: {}".format(e))
        try:
            conn2 = psycopg2.connect(host=settings.db_host, database=settings.db_db,
                                     user=settings.db_user, password=settings.db_password,
                                     connect_timeout=60)
            conn2.autocommit = True
            db_cursor2 = conn2.cursor()
            db_cursor2.execute("UPDATE folders SET processing_md5 = 'f' WHERE folder_id = %(folder_id)s",
                               {'folder_id': folder_id})
            conn2.close()
        except Exception as e:
            print(e)
        # Compress logs
        compress_log(filecheck_dir)
        sys.exit(1)


sys.exit(0)
