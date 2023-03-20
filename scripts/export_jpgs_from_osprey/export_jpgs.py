#!/usr/bin/env python3
#
# Export JPGs from a project or folder
#
############################################
# Import modules
############################################
import sys
import shutil
import locale

# For Postgres
import psycopg2

# Import settings from settings.py file
import settings

ver = "0.2.0"

# Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')


if len(sys.argv) == 3:
    folder_id = sys.argv[1]
    export_to = sys.argv[2]
else:
    folder_id = None
    export_to = settings.project_id


############################################
def main():
    # Connect to the database
    conn = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, connect_timeout = 60)
    conn.autocommit = True
    db_cursor = conn.cursor()
    if folder_id is None:
        # Get project's files
        db_cursor.execute("SELECT file_id, file_name, folder_id FROM files WHERE folder_id in (SELECT folder_id FROM folders WHERE project_id = %(project_id)s)", {'project_id': settings.project_id})
    else:
        # Get project's files
        db_cursor.execute(
            "SELECT file_id, file_name, folder_id FROM files WHERE folder_id = %(folder_id)s",
            {'folder_id': folder_id})
    files = db_cursor.fetchall()
    for file in files:
        print('file: {}'.format(file[1]))
        shutil.copy("{}/folder{}/{}.jpg".format(settings.jpgs_folder, file[2], file[0]), "{}/{}.jpg".format(export_to, file[1]))
    # Disconnect from db
    conn.close()
    return


############################################
# Main loop
############################################
if __name__=="__main__":
    main()
    

sys.exit(0)
