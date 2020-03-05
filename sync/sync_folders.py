#!/usr/bin/env python3
#
# Osprey script 
#
# Validate products from a vendor, usually images
#
############################################
# Import modules
############################################
import os, sys, subprocess, locale, logging, glob, time
from time import localtime, strftime
#For Postgres
import psycopg2

ver = "0.1.0"

##Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')


##Import settings from settings.py file
import settings



############################################
# Logging
############################################
if not os.path.exists('logs'):
    os.makedirs('logs')
current_time = strftime("%Y%m%d%H%M%S", localtime())
logfile_name = '{}.log'.format(current_time)
logfile = 'logs/{logfile_name}'.format(logfile_name = logfile_name)
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
#logging.getLogger('').addHandler(console)
logger1 = logging.getLogger("sync")
logging.getLogger('sync').addHandler(console)
logger1.info("sync version {}".format(ver))




############################################
# Functions
############################################

def compress_log():
    """
    Compress log files
    """
    os.chdir('logs')
    for file in glob.glob('*.log'):
        subprocess.run(["zip", "{}.zip".format(file), file])
        os.remove(file)
    os.chdir('../')
    return True



def sync_folders(project_id, folder_path, folder_name, destination_path, db_cursor, loggerfile):
    """
    Syncs folders between locations using rsync
    """
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
