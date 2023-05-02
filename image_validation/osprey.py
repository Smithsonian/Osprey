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
# import logging.handlers
# from logging.handlers import RotatingFileHandler
import time
# import random
# import sys
# import os

# import requests

# Import settings from settings.py file
import settings

# Import helper functions
from functions import *

ver = "2.0.0"

############################################
# Logging
############################################
log_folder = "logs"

if not os.path.exists(log_folder):
    os.makedirs(log_folder)
current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
logfile_folder = '{script_path}/{log_folder}/{curtime}'.format(script_path=os.getcwd(), log_folder=log_folder, curtime=current_time)
if not os.path.exists(logfile_folder):
    os.makedirs(logfile_folder)
logfile = '{logfile_folder}/osprey.log'.format(logfile_folder=logfile_folder)
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M:%S')
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
if check_requirements(settings.jhove) is False:
    logger.error("JHOVE was not found")
    sys.exit(1)


if check_requirements(settings.exiftool) is False:
    logger.error("exiftool was not found")
    sys.exit(1)


############################################
# Main
############################################
def main():
    # Check that the paths are valid dirs and are mounted
    if not os.path.isdir(settings.project_datastorage):
        logger.error("Path not found: {}".format(settings.project_datastorage))
        sys.exit(1)
    # Update project
    payload = {'api_key': settings.api_key}
    r = requests.post('{}/api/projects/{}'.format(settings.api_url, settings.project_alias), data=payload)
    if r.status_code != 200:
        # Something went wrong
        query_results = json.loads(r.text.encode('utf-8'))
        logger.error("API Returned Error: {}".format(query_results))
        sys.exit(1)
    project_info = json.loads(r.text.encode('utf-8'))
    # If project_checks are different here, update the database
    project_checks = ','.join([','.join(settings.project_file_checks), 'unique_file', 'md5'])
    if project_info['project_checks'] != project_checks:
        payload = {'type': 'project', 'api_key': settings.api_key, 'property': 'checks', 'value': project_checks}
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias), data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            sys.exit(1)
    # If project_postprocessing are different here, update the database
    if project_info['project_postprocessing'] != ','.join(settings.project_postprocessing):
        payload = {'type': 'project', 'api_key': settings.api_key, 'property': 'post', 'value': ','.join(settings.project_postprocessing)}
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias), data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            sys.exit(1)
    # If project_datastorage is different here, update the database
    if project_info['project_datastorage'] != settings.project_datastorage:
        payload = {'type': 'project', 'api_key': settings.api_key, 'property': 'storage',
                   'value': settings.project_datastorage}
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                          data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            sys.exit(1)
    # Loop each project path
    logger.debug('project_path: {}'.format(settings.project_datastorage))
    # Generate list of folders in the path
    folders = []
    for entry in os.scandir(settings.project_datastorage):
        if entry.is_dir() and entry.path != settings.project_datastorage:
            print(entry)
            folders.append(entry.path)
        else:
            logger.error("Extraneous files in: {}".format(entry.path))
            sys.exit(1)
    # No folders found
    if len(folders) == 0:
        logger.info("No folders found in: {}".format(settings.project_datastorage))
        return
    # Check each folder
    for folder in folders:
        run_checks_folder_p(project_info, folder, logfile_folder, logger)
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
                if settings.sleep is False:
                    logger.info("Process completed!")
                    compress_log()
                    sys.exit(0)
                else:
                    logger.info("Sleeping for {} secs".format(settings.sleep))
                    # Sleep before trying again
                    time.sleep(settings.sleep)
                    continue
            except KeyboardInterrupt:
                logger.info("Ctrl-c detected. Leaving program.")
                compress_log()
                sys.exit(0)
            except Exception as e:
                logger.error("There was an error: {}".format(e))
                compress_log()
                sys.exit(1)


sys.exit(0)
