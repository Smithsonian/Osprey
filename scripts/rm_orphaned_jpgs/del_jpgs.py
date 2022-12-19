#!/usr/bin/env python3
#
# delete orphaned jpg files 
#
############################################
# Import modules
############################################
import os, sys, shutil, locale, glob
#For Postgres
import psycopg2
from time import localtime, strftime

ver = "0.1.0"

##Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')


##Import settings from settings.py file
import settings




############################################
def main():
    #Connect to the database
    conn = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, connect_timeout = 60)
    conn.autocommit = True
    db_cursor = conn.cursor()
    #Loop each project path
    folders = []
    for entry in os.scandir(settings.jpg_path):
        if entry.is_dir():
            folders.append(entry.path)
    for jpgpath in folders:
        print('jpgpath: {}'.format(jpgpath))
        #Generate list of folders in the path
        #Run each folder
        os.chdir(jpgpath)
        files = glob.glob("*.jpg")
        for file in files:
            db_cursor.execute("SELECT count(*) FROM files WHERE file_id = %(file_id)s", {'file_id': file.replace(".jpg", "")})
            file_id = db_cursor.fetchone()
            if file_id == 0:
                print("Deleting {}".format(file))
                os.remove(file)
            else:
                print("File OK {}".format(file))
                continue
    #Disconnect from db
    conn.close()
    return




############################################
# Main loop
############################################
if __name__=="__main__":
    main()
    


sys.exit(0)
