#!/usr/bin/env python3
#
# Osprey script
# https://github.com/Smithsonian/Osprey
#
# Validate images in Digitization Projects
#
############################################
# Import modules
############################################
import logging
import time
import requests

# Import settings from settings.py file
import settings

# Import helper functions
from functions import *

ver = "2.5.0"

# Pass an argument in the CLI 'debug'
if len(sys.argv) > 1:
    run_debug = sys.argv[1]
else:
    run_debug = False


############################################
# Logging
############################################
log_folder = "logs"

if not os.path.exists(log_folder):
    os.makedirs(log_folder)
# current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
# logfile_folder = '{script_path}/{log_folder}/{curtime}'.format(script_path=os.getcwd(), log_folder=log_folder, curtime=current_time)
# if not os.path.exists(logfile_folder):
#     os.makedirs(logfile_folder)
# logfile = '{logfile_folder}/osprey.log'.format(logfile_folder=logfile_folder)
# logging.basicConfig(filename=logfile, filemode='a', level=logging.DEBUG,
#                     format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
#                     datefmt='%y-%b-%d %H:%M:%S')
# logger = logging.getLogger("osprey")
# stdout = logging.StreamHandler(stream=sys.stdout)
# console = logging.StreamHandler()
# if run_debug == 'debug':
#     console.setLevel(logging.DEBUG)
# else:
#     console.setLevel(logging.INFO)
# formatter = logging.Formatter('%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s')
# console.setFormatter(formatter)
# logging.getLogger('osprey').addHandler(console)
#
# logger.info("osprey version {}".format(ver))

# Logging
current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
logfile = '{}/{}.log'.format(log_folder, current_time)
logging.basicConfig(filename=logfile, filemode='a', level=logging.DEBUG,
                    format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
                    datefmt='%y-%b-%d %H:%M:%S')
logger = logging.getLogger("osprey")

logging.info("osprey version {}".format(ver))

# Set locale for number format
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')


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
    r = requests.get('{}/api/'.format(settings.api_url))
    if r.status_code != 200:
        # Something went wrong
        query_results = r.text.encode('utf-8')
        logger.error("API Returned Error: {}".format(query_results))
        sys.exit(1)
    system_info = json.loads(r.text.encode('utf-8'))
    if system_info['sys_ver'] != ver:
        logger.error("API version ({}) does not match this script ({})".format(system_info['sys_ver'], ver))
        sys.exit(1)
    payload = {'api_key': settings.api_key}
    r = requests.post('{}/api/projects/{}'.format(settings.api_url, settings.project_alias), data=payload)
    if r.status_code != 200:
        # Something went wrong
        query_results = r.text.encode('utf-8')
        logger.error("API Returned Error: {}".format(query_results))
        sys.exit(1)
    project_info = json.loads(r.text.encode('utf-8'))
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
        return True
    # Check each folder
    logger.info("project_info: {}".format(project_info))
    for folder in folders:
        run_checks_folder_p(project_info, folder, log_folder, logger)
    return True


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
