#!/usr/bin/env python3
#
# Export reports of the folders to spreadsheets
#   mostly to use in Dropbox or similar.
#  Needs to be run with cron to update the files.
#
############################################
# Import modules
############################################
import sys
import locale
import json
import os
import requests
import pandas as pd
from openpyxl import Workbook

# Import settings from settings.py file
import settings

ver = "0.1.0"

# Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')

if os.path.exists(settings.export_to) is False:
    print(" Error, export location ({}) was not found.".format(settings.export_to))
    sys.exit(1)


############################################
def main():
    payload_api = {'api_key': settings.api_key}
    r = requests.post('{}/api/projects/{}'.format(settings.api_url, settings.project_alias), data=payload_api)
    if r.status_code != 200:
        # Something went wrong
        query_results = r.text.encode('utf-8')
        print("API Returned Error: {}".format(query_results))
        sys.exit(1)

    project_info = json.loads(r.text.encode('utf-8'))
    project_checks = project_info['project_checks']
    project_checks = project_checks.split(',')
    filename = "{}/project_status.xlsx".format(settings.export_to)
    workbook = Workbook()
    sheet = workbook.active

    i = 1
    for attrib, value in project_info.items():
        # print("{}: {}".format(attrib, value))
        if attrib == "folders" or attrib == "reports":
            continue
        elif attrib == "project_stats":
            sheet["A{}".format(i)] = "images_taken"
            sheet["B{}".format(i)] = value['images_taken']
            i += 1
            sheet["A{}".format(i)] = "objects_digitized"
            sheet["B{}".format(i)] = value['objects_digitized']
            i += 1
            continue
        if value == "":
            continue
        sheet["A{}".format(i)] = attrib
        sheet["B{}".format(i)] = value
        i += 1

    workbook.save(filename=filename)

    folders_storage = "{}/folders".format(settings.export_to)
    if not os.path.exists(folders_storage):
        os.makedirs(folders_storage)

    for folder in project_info['folders']:
        folder_id = folder['folder_id']
        r = requests.post('{}/api/folders/{}'.format(settings.api_url, folder_id), data=payload_api)
        if r.status_code != 200:
            # Something went wrong
            query_results = r.text.encode('utf-8')
            print("API Returned Error: {}".format(query_results))
            sys.exit(1)

        folder_info = json.loads(r.text.encode('utf-8'))
        file_df = pd.DataFrame(folder_info['files'])
        # cols = ['file_id', 'file_name', 'file_timestamp', 'preview_image', 'updated_at']
        cols = ['file_id', 'file_name', 'file_timestamp', 'updated_at']
        for pcheck in project_checks:
            cols.append(pcheck)
        filename = "{}/{}.xlsx".format(folders_storage, folder_info['folder'])
        file_df.to_excel(filename, columns=cols, header=True, index=False)


############################################
# Main loop
############################################
if __name__=="__main__":
    main()
    

sys.exit(0)
