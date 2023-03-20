#!/usr/bin/env python3
#
# Export JPGs from a project
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
    #Get project's files
    db_cursor.execute("SELECT file_id, file_name FROM files WHERE folder_id in (SELECT folder_id FROM folders WHERE project_id = %(project_id)s) ORDER BY RANDOM() LIMIT %(limit)s", {'project_id': settings.project_id, 'limit': settings.limit})
    files = db_cursor.fetchall()
    for file in files:
        print('file: {}'.format(file[1]))
        shutil.copy("{}/{}/{}.jpg".format(settings.jpgs_folder, str(file[0])[0:2], file[0]), "{}/{}.jpg".format(settings.project_id, file[1]))
    #Disconnect from db
    conn.close()
    return



# def main():
#     #Connect to the database
#     conn = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, connect_timeout = 60)
#     conn.autocommit = True
#     db_cursor = conn.cursor()
#     #Get project's files
#     db_cursor.execute("SELECT file_name FROM files WHERE folder_id in (SELECT folder_id FROM folders WHERE project_id = %(project_id)s) and file_name like {} ORDER BY RANDOM() LIMIT %(limit)s".format("'%%-001'"), {'project_id': settings.project_id, 'limit': settings.limit})
#     files = db_cursor.fetchall()
#     for file in files:
#         db_cursor.execute("SELECT file_id FROM files WHERE folder_id in (SELECT folder_id FROM folders WHERE project_id = %(project_id)s) and file_name = %(file_name)s", {'project_id': settings.project_id, 'file_name': file[0]})
#         file_id = db_cursor.fetchone()[0]
#         db_cursor.execute("SELECT file_id FROM files WHERE folder_id in (SELECT folder_id FROM folders WHERE project_id = %(project_id)s) and file_name = %(file_name)s", {'project_id': settings.project_id, 'file_name': file[0].replace('-001', '-002')})
#         file_2 = db_cursor.fetchone()[0]
#         print('file: {}'.format(file[0]))
#         shutil.copy("{}/{}/{}.jpg".format(settings.jpgs_folder, str(file_id)[0:2], file_id), "{}/{}.jpg".format(settings.project_id, file[0]))
#         shutil.copy("{}/{}/{}.jpg".format(settings.jpgs_folder, str(file_2)[0:2], file_2), "{}/{}.jpg".format(settings.project_id, file[0].replace('-001', '-002')))
#     #Disconnect from db
#     conn.close()
#     return



############################################
# Main loop
############################################
if __name__=="__main__":
    main()
    


sys.exit(0)