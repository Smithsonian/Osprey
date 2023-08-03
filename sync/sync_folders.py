#!/usr/bin/env python3
#
# Script to sync files 
#
# Usually gets files from a vendor when the folders have MD5 files,
#   indicating that the folder is delivered.
#
############################################
# Import modules
############################################
import os, sys, subprocess, locale, logging, glob, time
from time import localtime, strftime

ver = "0.2.0"

# Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')

# Import settings from settings.py file
import settings


############################################
# Logging
############################################
current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
logfile = '{}/sync_{}.log'.format(settings.log_folder, current_time)
logging.basicConfig(filename=logfile, filemode='a', level=logging.DEBUG,
                    format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
                    datefmt='%y-%b-%d %H:%M:%S')
logger = logging.getLogger("sync")

logging.info("script_ver = {}".format(ver))


############################################
# Functions
############################################

def compress_log():
    """
    Compress log files
    """
    cur_dir = os.getcwd()
    os.chdir(settings.log_folder)
    for file in glob.glob('*.log'):
        subprocess.run(["zip", "{}.zip".format(file), file])
        os.remove(file)
    os.chdir(cur_dir)
    return True



def sync_folders(source_path, destination_path, logger):
    """
    Syncs folders between locations using rsync
    """
    folders = []
    for entry in os.scandir(settings.source_path):
        if entry.is_dir() and entry.path != settings.source_path:
            print(entry)
            folders.append(entry.path)
        else:
            logger.error("Extraneous files in: {}".format(entry.path))
            sys.exit(1)
    # No folders found
    if len(folders) == 0:
        logger.info("No folders found in: {}".format(settings.project_datastorage))
        return True
    # Check each folder
    for folder in folders:
        subfolders = []
        for subentry in os.scandir(folder):
            if subentry.is_dir() and subentry.path != folder:
                print(subentry)
                subfolders.append(subentry.path)
            else:
                logger.error("Extraneous files in: {}".format(subentry.path))
                sys.exit(1)
        if settings.req_md5:
            for subf in subfolders:
                if len(glob.glob(subf + "/*.md5")) != 1:
                    # Subfolder missing md5, skip
                    break
            p = subprocess.Popen(['rsync', '-avht', '--delete', folder, settings.destination_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out,err) = p.communicate()
            if p.returncode != 0:
                loggerfile.error("Error running rsync for {} ({}; {})".format(folder, out, err))
                return False
            else:
                return True
        md5_exists = 0
    else:
        run_checks_folder_p(project_info, folder, log_folder, logger)


        
    db_cursor.execute("SELECT folder_id, delivered_to_dams FROM folders WHERE project_folder = %(project_folder)s and project_id = %(project_id)s", {'project_folder': folder_name, 'project_id': project_id})
    loggerfile.debug(db_cursor.query.decode("utf-8"))
    folder_info = db_cursor.fetchone()
    if folder_info == None:
        do_sync = True
    else:
        if folder_info[1] == 9:
            do_sync = True
        else:
            do_sync = False
    loggerfile.debug("folder: {}|do_sync: {}".format(folder_path, do_sync))
    if do_sync == False:
        loggerfile.info("Skipping folder: {}".format(folder_path))
        return
    else:
        loggerfile.info("Sync folder: {}".format(folder_path))
        #Don't re-invent the wheel, use rsync
        p = subprocess.Popen(['rsync', '-avht', '--delete', folder_path, destination_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out,err) = p.communicate()
        if p.returncode != 0:
            loggerfile.error("Could not sync {}".format(folder_path))
            return False
        else:
            return True



def main():
    #Check that the paths are mounted
    for p_path in settings.project_paths:
        if os.path.isdir(p_path) == False:
            logger1.error("Path not found: {}".format(p_path))
            sys.exit(1)
    #Connect to the database
    logger1.info("Connecting to database")
    conn = psycopg2.connect(
                host = settings.db_host, 
                    database = settings.db_db, 
                    user = settings.db_user, 
                    connect_timeout = 60)
    conn.autocommit = True
    db_cursor = conn.cursor()
    for project_path in settings.project_paths:
        #Generate list of folders in the path
        folders = []
        for entry in os.scandir(project_path):
            if entry.is_dir():
                folders.append(entry.path)
        #No folders found
        if len(folders) == 0:
            continue
        #Run each folder
        for folder in folders:
            folder_path = folder
            logger1.debug(folder_path)
            folder_name = os.path.basename(folder)
            sync_folders(settings.project_id, folder_path, folder_name, settings.destination_path, db_cursor, logger1)
    conn.close()
    logger1.info("Sleeping for {} secs".format(settings.sleep))
    #Sleep before trying again
    time.sleep(settings.sleep)





############################################
# Main loop
############################################
if __name__=="__main__":
    while True:
        #main()
        try:
            main()
        except KeyboardInterrupt:
            print("Ctrl-c detected. Leaving program.")
            #Compress logs
            compress_log()
            sys.exit(0)
        except Exception as e:
            print("There was an error: {}".format(e))
            #Compress logs
            compress_log()
            sys.exit(1)



sys.exit(0)
