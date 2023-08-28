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
import json
import requests
import random
import math

# Import settings from settings.py file
import settings

ver = "0.3.1"

# Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')

if len(sys.argv) == 3:
    sample_size = None
    folder_id = sys.argv[2]
    export_to = sys.argv[1]
elif len(sys.argv) == 4:
    sample_size = sys.argv[3]
    folder_id = sys.argv[2]
    export_to = sys.argv[1]
else:
    print("Usage: ./export_jpgs.py [destination] [folder_id] [percent_sample - optional]")
    sys.exit(1)


############################################
def main():
    r = requests.post('{}/api/folders/{}'.format(settings.api_url, folder_id))
    if r.status_code != 200:
        # Something went wrong
        query_results = r.text.encode('utf-8')
        print("API Returned Error: {}".format(query_results))
        sys.exit(1)
    folder_info = json.loads(r.text.encode('utf-8'))
    if sample_size is None:
        for file in folder_info['files']:
            print('file: {}'.format(file['file_name']))
            shutil.copy("{}/folder{}/{}.jpg".format(settings.jpgs_folder, folder_id, file['file_id']),
                        "{}/{}.jpg".format(export_to, file['file_name']))
    else:
        files_sample = math.ceil(len(folder_info['files']) * (float(sample_size) / 100.0))
        files = random.sample(folder_info['files'], files_sample)
        for file in files:
            print('file: {}'.format(file['file_name']))
            shutil.copy("{}/folder{}/{}.jpg".format(settings.jpgs_folder, folder_id, file['file_id']),
                        "{}/{}.jpg".format(export_to, file['file_name']))
    return


############################################
# Main loop
############################################
if __name__ == "__main__":
    main()

sys.exit(0)
