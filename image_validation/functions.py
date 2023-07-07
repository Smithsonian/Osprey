# Functions for osprey.py
from datetime import datetime
import os
import stat
import subprocess
import xmltodict
import sys
import json
import requests

from random import randint

import glob
from PIL import Image
from subprocess import PIPE
from pathlib import Path
import shutil
import locale
import itertools

# For MD5
import hashlib

# Parallel
from multiprocessing import Pool

# Get settings and queries
import settings

# Remove DecompressionBombWarning due to large files
# by using a large threshold
# https://github.com/zimeon/iiif/issues/11
Image.MAX_IMAGE_PIXELS = 1000000000


def check_requirements(program):
    """
    Check if required programs are installed
    """
    # From https://stackoverflow.com/a/34177358
    from shutil import which
    return which(program) is not None


def compress_log():
    """
    Compress log files
    """
    filecheck_dir = os.path.dirname(__file__)
    os.chdir('{}/logs'.format(filecheck_dir))
    folders = []
    for entry in os.scandir('.'):
        if entry.is_dir():
            folders.append(entry.path)
    # No folders found
    if len(folders) == 0:
        return None
    # Compress each folder
    for folder in folders:
        subprocess.run(["zip", "-r", "{}.zip".format(folder), folder])
        shutil.rmtree(folder)
    os.chdir(filecheck_dir)
    return True


def jhove_validate(file_path, logger):
    """
    Validate the file with JHOVE
    """
    # Where to write the results
    xml_file = "{}/jhove_{}.xml".format(settings.tmp_folder, randint(100, 100000))
    if os.path.isfile(xml_file):
        os.unlink(xml_file)
    # Setting JHOVE module
    file_extension = Path(file_path).suffix.lower()
    if file_extension == ".tif" or file_extension == ".tiff":
        jhove_module = "TIFF-hul"
    elif file_extension == ".jpg" or file_extension == ".jpeg":
        jhove_module = "JPEG-hul"
    elif file_extension == ".jp2":
        jhove_module = "JPEG2000-hul"
    else:
        logger.error("jhove_error - extension: {}".format(file_extension, ))
        sys.exit(1)
    # Run JHOVE
    p = subprocess.Popen([settings.jhove, "-m", jhove_module, "-h", "xml", "-o", xml_file, file_path],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    # Open and read the results xml
    try:
        with open(xml_file) as fd:
            doc = xmltodict.parse(fd.read())
    except Exception as e:
        error_msg = "Could not find result file from JHOVE ({}) ({}) | {} - {}".format(xml_file, e, out, err)
        check_results = 1
        check_info = error_msg
        return check_results, check_info
    if os.path.isfile(xml_file):
        os.unlink(xml_file)
    # Get file status
    file_status = doc['jhove']['repInfo']['status']
    jhove_results = out.decode('latin-1')
    if file_status == "Well-Formed and valid":
        check_results = 0
        check_info = jhove_results
    else:
        check_results = 1
        if len(doc['jhove']['repInfo']['messages']) == 1:
            # If the only error is with the WhiteBalance, ignore
            # Issue open at Github, seems will be fixed in future release
            # https://github.com/openpreserve/jhove/issues/364
            if doc['jhove']['repInfo']['messages']['message']['#text'][:31] == "WhiteBalance value out of range":
                check_results = 0
        file_status = doc['jhove']['repInfo']['messages']['message']['#text']
        check_info = "{}; {}".format(file_status, jhove_results)
    return check_results, check_info


def magick_validate(file_id, filename, logger, paranoid=False):
    """
    Validate the file with Imagemagick
    """
    if paranoid:
        p = subprocess.Popen(['identify', '-verbose', '-regard-warnings', filename], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env={"MAGICK_THREAD_LIMIT": "1"})
    else:
        p = subprocess.Popen(['identify', '-verbose', filename], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env={"MAGICK_THREAD_LIMIT": "1"})
    (out, err) = p.communicate()
    if p.returncode == 0:
        magick_identify = 0
    else:
        magick_identify = 1
        logger.debug("magick_out: {} {}".format(file_id, out.decode('UTF-8')))
        logger.debug("magick_err: {} {}".format(file_id, err.decode('UTF-8')))
    magick_identify_info = out + err
    check_results = magick_identify
    check_info = magick_identify_info.decode('latin-1')
    return check_results, check_info


def tif_compression(file_path):
    """
    Check if the image has LZW compression
    """
    img = Image.open(file_path)
    check_info = img.info['compression']
    if check_info == 'tiff_lzw':
        check_results = 0
    else:
        check_results = 1
    # return True
    return check_results, check_info


def tifpages(file_path):
    """
    Check if TIF has multiple pages using Pillow
    """
    img = Image.open(file_path)
    no_pages = img.n_frames
    if no_pages == 1:
        check_results = 0
    else:
        check_results = 1
    check_info = "No. of pages: {}".format(no_pages)
    # return True
    return check_results, check_info


def get_file_exif(filename):
    """
    Extract the EXIF info from the RAW file
    """
    p = subprocess.Popen([settings.exiftool, '-j', '-L', '-a', '-U', '-u', '-D', '-G1', filename],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    exif_info = out
    return exif_info


def get_filemd5(filepath, logger):
    """
    Get MD5 hash of a file
    """
    md5_hash = hashlib.md5()
    if os.path.isfile(filepath):
        with open(filepath, "rb") as f:
            # Read and update hash in chunks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                md5_hash.update(byte_block)
        file_md5 = md5_hash.hexdigest()
    else:
        file_md5 = ""
    logger.debug("file_md5: {} {}".format(filepath, file_md5))
    return file_md5


def file_pair_check(file_id, filename, derivative_path, derivative_type):
    """
    Check if a file has a pair (main + raw)
    """
    file_stem = Path(filename).stem
    # Check if file pair is present
    derivative_file = glob.glob("{}/{}.*".format(derivative_path, file_stem))
    if len(derivative_file) == 1:
        derivative_file = derivative_file[0]
        file_pair = 0
        file_pair_info = "Raw file {} found for {} ({})".format(Path(derivative_file).name, filename, file_id)
    elif len(derivative_file) == 0:
        derivative_file = None
        # Raw file is missing
        file_pair = 1
        file_pair_info = "Missing raw file for {} ({})".format(filename, file_id)
    else:
        derivative_file = None
        # Raw file is missing
        file_pair = 1
        file_pair_info = "Multiple raw files for {} ({})".format(filename, file_id)
    return file_pair, file_pair_info, derivative_file


# def checkmd5file(md5_file, folder_id, filetype, db_cursor):
#     """
#     Check if md5 hashes match with the files
#     -In progress
#     """
#     md5_error = ""
#     db_cursor.execute(queries.select_tif_md5, {'folder_id': folder_id, 'filetype': filetype})
#     db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
#                                            'log_area': 'process_image',
#                                            'log_text': db_cursor.query.decode("utf-8")})
#     vendor = pandas.DataFrame(db_cursor.fetchall(), columns=['md5_1', 'filename'])
#     md5file = pandas.read_csv(md5_file, header=None, names=['md5_2', 'filename'], index_col=False, sep="  ")
#     # Remove suffix
#     # if filetype == "tif":
#     #     md5file['filename'] = md5file['filename'].str.replace(".tif", "")
#     #     md5file['filename'] = md5file['filename'].str.replace(".TIF", "")
#     # elif filetype == "raw":
#     #     md5file['filename'] = md5file['filename'].str.replace(".{}".format(settings.raw_files.lower()), "")
#     #     md5file['filename'] = md5file['filename'].str.replace(".{}".format(settings.raw_files.upper()), "")
#     md5check = pandas.merge(vendor, md5file, how="outer", on="filename")
#     # MD5 hashes don't match
#     # Get rows where MD5 don't match
#     md5check_match = md5check[md5check.md5_1 != md5check.md5_2]
#     # Ignore NAs
#     md5check_match = md5check_match.dropna()
#     # check if there are any mismatches
#     nrows = len(md5check_match)
#     if nrows > 0:
#         md5_error = md5_error + "There were {} files where the MD5 hash did not match:".format(nrows)
#         for i in range(0, nrows):
#             md5_error = md5_error + "\n - File: {}, MD5 of file: {}, hash in file: {}".format(
#                 md5check_match['filename'][i], md5check_match['md5_2'], md5check_match['md5_1'])
#     # Extra files in vendor mount
#     vendor_extras = vendor[~vendor.filename.isin(md5file.filename)]['filename']
#     # Extra files in md5file
#     md5file_extras = md5file[~md5file.filename.isin(vendor.filename)]['filename']
#     return True


# def check_stitched_jpg(file_id, filename, db_cursor, logger):
#     """
#     Run checks for jpg files that were stitched from 2 images
#     """
#     p = subprocess.Popen(['identify', '-verbose', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={"MAGICK_THREAD_LIMIT": "1"})
#     (out, err) = p.communicate()
#     if p.returncode == 0:
#         magick_identify = 0
#         magick_identify_info = out
#         magick_return = True
#     else:
#         magick_identify = 1
#         magick_identify_info = err
#         magick_return = False
#         logger.debug("stitched_out: {} {}".format(file_id, out.decode('UTF-8')))
#         logger.debug("stitched_err: {} {}".format(file_id, err.decode('UTF-8')))
#     db_cursor.execute(queries.file_check,
#                       {'file_id': file_id,
#                        'folder_id': folder_id,
#                        'file_check': 'stitched_jpg',
#                        'check_results': magick_identify,
#                        'check_info': magick_identify_info.decode("utf-8").replace("'", "''")})
#     if magick_return:
#         # Store MD5
#         file_md5 = filemd5(filename, logger)
#         db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'jpg', 'md5': file_md5})
#     return True


def jpgpreview(file_id, folder_id, file_path, logger):
    """
    Create preview image
    """
    if settings.jpg_previews == "":
        logger.error("JPG preview folder is not set in settings file")
        sys.exit(1)
    disk_check = shutil.disk_usage(settings.jpg_previews)
    if (disk_check.free / disk_check.total) < settings.jpg_previews_free:
        logger.error("JPG storage location is running out of space ({}%) - {}".format(
                                                   round(disk_check.free / disk_check.total, 4) * 100,
                                                    settings.jpg_previews))
        sys.exit(1)
    preview_file_path = "{}/folder{}".format(settings.jpg_previews, str(folder_id))
    preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
    # Create subfolder if it doesn't exists
    if not os.path.exists(preview_file_path):
        os.makedirs(preview_file_path)
    # Delete old image, if exists
    if os.path.isfile(preview_image):
        return True
    img = Image.open(file_path)
    if settings.previews_size == "full":
        img.save(preview_image, 'jpeg', icc_profile=img.info.get('icc_profile'))
    else:
        width_o, height_o = img.size
        width = settings.previews_size
        height = round(height_o * (width / width_o))
        newsize = (width, height)
        im1 = img.resize(newsize)
        im1.save(preview_image, 'jpeg', icc_profile=img.info.get('icc_profile'))
    if os.path.isfile(preview_image):
        os.chmod(preview_image, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        return True
    else:
        logger.error("File:{}|msg:{}".format(file_path, out))
        sys.exit(1)
        return False


def update_folder_stats(folder_id, folder_path, logger):
    """
    Update the stats for the folder
    """
    payload = {'type': 'folder',
               'folder_id': folder_id,
               'api_key': settings.api_key,
               'property': 'stats',
               'value': '0'
               }
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    logger.info("update_folder_stats: {}".format(query_results))
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        sys.exit(1)
    if len(glob.glob(folder_path + "/" + settings.main_files_path + "/*.md5")) == 1:
        md5_exists = 0
    else:
        md5_exists = 1
    payload = {'type': 'folder',
               'folder_id': folder_id,
               'api_key': settings.api_key,
               'property': 'md5_exists',
               'value': 'tif'
               }
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    logger.info("query_results: {}".format(query_results))
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        sys.exit(1)
    if len(glob.glob(folder_path + "/" + settings.raw_files_path + "/*.md5")) == 1:
        md5_raw_exists = 0
    else:
        md5_raw_exists = 1
    payload = {'type': 'folder',
               'folder_id': folder_id,
               'api_key': settings.api_key,
               'property': 'md5_exists',
               'value': 'raw'
               }
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    logger.info("query_results: {}".format(query_results))
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        sys.exit(1)
    return True


# def file_checks_summary(file_id, db_cursor, logger):
#     file_checks = 0
#     for filecheck in settings.project_file_checks:
#         db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': filecheck})
#         logger.debug(db_cursor.query.decode("utf-8"))
#         result = db_cursor.fetchone()
#         if result is None:
#             db_cursor.execute(queries.file_check,
#                               {'file_id': file_id,
#                                'folder_id': folder_id,
#                                'file_check': filecheck,
#                                'check_results': 9,
#                                'check_info': ''})
#             logger.debug(db_cursor.query.decode("utf-8"))
#             result = 1
#         else:
#             result = result[0]
#             if result == 9:
#                 result = 1
#         file_checks = file_checks + result
#     # Nothing to do, return
#     return file_checks


def run_checks_folder_p(project_info, folder_path, logfile_folder, logger):
    """
    Process a folder in parallel
    """
    project_id = project_info['project_alias']
    logger.info("Processing folder: {}".format(folder_path))
    folder_name = os.path.basename(folder_path)
    # Check if the folder exists in the database
    folder_id = None
    if len(project_info['folders']) > 0:
        for folder in project_info['folders']:
            logger.info("folder: {}".format(folder))
            logger.info("FOLDER NEW: {}|{}|{}|{}|{}|{}".format(folder['folder'], folder_name, folder['folder_path'], folder_path, folder['folder'] == folder_name, folder['folder_path'] == folder_path))
            if folder['folder'] == folder_name and folder['folder_path'] == folder_path:
                folder_info = folder
                folder_id = folder_info['folder_id']
                delivered_to_dams = folder_info['delivered_to_dams']
                logger.info("Folder exists: {}".format(folder_id))
                break
    if folder_id is None:
        # CREATE FOLDER
        folder_date = settings.folder_date(folder_name)
        payload = {
            'type': 'folder',
            'api_key': settings.api_key,
            'folder': folder_name,
            'folder_path': folder_path,
            'folder_date': folder_date,
            'project_id': project_info['project_id']
        }
        r = requests.post('{}/api/new/{}'.format(settings.api_url, settings.project_alias),
                          data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        logger.info("Creating folder record: {} - {} - {}".format(folder_path, payload, query_results))
        if query_results["result"] is False:
            logger.error("API Returned Error: {}".format(query_results))
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            sys.exit(1)
        else:
            folder_id = query_results["result"][0]['folder_id']
            delivered_to_dams = 9
    # if folder_id is None:
    if 'folder_id' not in locals():
        logger.error("Could not get folder_id for {}".format(folder_name))
        sys.exit(1)
    # Check if folder is ready or in DAMS
    if delivered_to_dams == 0 or delivered_to_dams == 1:
        # Folder ready for or delivered to DAMS, skip
        logger.info("Folder ready for or delivered to for DAMS, skipping {}".format(folder_path))
        return folder_id
    payload = {'type': 'folder', 'folder_id': folder_id, 'api_key': settings.api_key, 'property': 'status0',
               'value': ''}
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    logger.info(query_results)
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        sys.exit(1)
    if os.path.isdir("{}/{}".format(folder_path, settings.main_files_path)) is False:
        folder_status_msg = "Missing MAIN folder in {}".format(folder_path)
        logger.info(folder_status_msg)
        payload = {'type': 'folder', 'folder_id': folder_id, 'api_key': settings.api_key, 'property': 'status9',
                   'value': folder_status_msg}
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                          data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            sys.exit(1)
        return folder_id
    else:
        logger.info("MAIN folder found in {}".format(folder_path))
        folder_full_path = "{}/{}".format(folder_path, settings.main_files_path)
        folder_full_path_files = glob.glob("{}/*".format(folder_full_path))
        folder_raw_path = "{}/{}".format(folder_path, settings.raw_files_path)
        folder_raw_path_files = glob.glob("{}/*".format(folder_raw_path))
        if len(folder_full_path_files) != len(folder_raw_path_files):
            folder_status_msg = "No. of files do not match (main: {}, raw: {})".format(len(folder_full_path_files), len(folder_raw_path_files))
            payload = {'type': 'folder', 'folder_id': folder_id, 'api_key': settings.api_key, 'property': 'status1',
                       'value': folder_status_msg}
            r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                              data=payload)
            query_results = json.loads(r.text.encode('utf-8'))
            if query_results["result"] is not True:
                logger.error("API Returned Error: {}".format(query_results))
                logger.error("Request: {}".format(str(r.request)))
                logger.error("Headers: {}".format(r.headers))
                logger.error("Payload: {}".format(payload))
                sys.exit(1)
        os.chdir(folder_full_path)
        # Get all files in the folder
        files = glob.glob("*.*")
        # Remove md5 files from list
        files = [file for file in files if Path(file).suffix != '.md5']
        if len(files) > 0:
            preview_file_path = "{}/folder{}".format(settings.jpg_previews, str(folder_id))
            # Create subfolder if it doesn't exists
            if not os.path.exists(preview_file_path):
                os.makedirs(preview_file_path)
        ###############
        # Parallel
        ###############
        no_tasks = len(files)
        if settings.no_workers == 1:
            print_str = "Started run of {notasks} tasks"
            print_str = print_str.format(notasks=str(locale.format_string("%d", no_tasks, grouping=True)))
            logger.info(print_str)
            # Process files in parallel
            for file in files:
                process_image_p(file, folder_path, folder_id, project_id, logfile_folder)
        else:
            print_str = "Started parallel run of {notasks} tasks on {workers} workers"
            print_str = print_str.format(notasks=str(locale.format_string("%d", no_tasks, grouping=True)), workers=str(
                settings.no_workers))
            logger.info(print_str)
            # Process files in parallel
            inputs = zip(files, itertools.repeat(folder_path), itertools.repeat(folder_id), itertools.repeat(project_id), itertools.repeat(logfile_folder))
            with Pool(settings.no_workers) as pool:
                pool.starmap(process_image_p, inputs)
                pool.close()
                pool.join()
    # Update folder stats
    update_folder_stats(folder_id, folder_path, logger)
    return folder_id


def process_image_p(filename, folder_path, folder_id, project_id, logfile_folder):
    """
    Run checks for image files
    """
    import settings
    import random
    import logging
    import time
    random_int = random.randint(1, 1000)
    # Logging
    current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    logfile = '{}/{}_{}.log'.format(logfile_folder, current_time, random_int)
    logging.basicConfig(filename=logfile, filemode='a', level=logging.DEBUG,
                        format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
                        datefmt='%y-%b-%d %H:%M:%S')
    logger = logging.getLogger("osprey_{}".format(random_int))
    #
    main_file_path = "{}/{}/{}".format(folder_path, settings.main_files_path, filename)
    logger.info("filename: {}".format(main_file_path))
    folder_id = int(folder_id)
    filename_stem = Path(filename).stem
    filename_suffix = Path(filename).suffix[1:]
    payload_api = {'api_key': settings.api_key}
    r = requests.post('{}/api/folders/{}'.format(settings.api_url, folder_id), data=payload_api)
    if r.status_code != 200:
        # Something went wrong
        logger.error("API ({}) Returned Error: {}".format('{}/api/folders/{}'.format(settings.api_url, folder_id), r.text))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        return False
    folder_info = json.loads(r.text.encode('utf-8'))
    r = requests.post('{}/api/projects/{}'.format(settings.api_url, settings.project_alias), data=payload_api)
    if r.status_code != 200:
        # Something went wrong
        query_results = r.text.encode('utf-8')
        logger.error("API Returned Error: {}".format(query_results))
        sys.exit(1)
    project_info = json.loads(r.text.encode('utf-8'))
    project_checks = project_info['project_checks']
    # Check if file exists, insert if not
    file_id = None
    for file in folder_info['files']:
        # logger.info("file: {}".format(file))
        if file['file_name'] == filename_stem:
            file_id = file['file_id']
            file_info = file
            break
    if file_id is None:
        # Get modified date for file
        file_timestamp_float = os.path.getmtime(main_file_path)
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        payload = {
                'api_key': settings.api_key,
                'type': "file",
                'folder_id': folder_id,
                'filename': filename_stem,
                'timestamp': file_timestamp
                }
        r = requests.post('{}/api/new/{}'.format(settings.api_url, settings.project_alias), data=payload)
        if r.status_code != 200:
            # Something went wrong
            logger.error("API Returned Error: {}".format(r.text))
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
        else:
            logger.info("API Returned: {}".format(r.text))
        file_info = json.loads(r.text.encode('utf-8'))['result']
        logging.debug("new_file:{}".format(file_info))
        file_id = file_info[0]['file_id']
        file_uid = file_info[0]['uid']
        # # Get filesize from TIF:
        file_size = os.path.getsize(main_file_path)
        filetype = filename_suffix.lower()
        payload = {
            'api_key': settings.api_key,
            'type': "filesize",
            'file_id': file_id,
            'filetype': filename_suffix.lower(),
            'filesize': file_size
        }
        r = requests.post('{}/api/new/{}'.format(settings.api_url, settings.project_alias), data=payload)
        if r.status_code != 200:
            # Something went wrong
            logger.error("API Returned Error: {}".format(r.text))
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
        # Refresh folder info
        r = requests.post('{}/api/folders/{}'.format(settings.api_url, folder_id), data=payload_api)
        if r.status_code != 200:
            # Something went wrong
            query_results = json.loads(r.text.encode('utf-8'))
            logger.error("API Returned Error: {}".format(query_results))
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
        folder_info = json.loads(r.text.encode('utf-8'))
        logger.info("folder_info:{}".format(folder_info))
        for file in folder_info['files']:
            if file['file_name'] == filename_stem:
                file_id = file['file_id']
                file_info = file
                break
    logging.debug("file_info: {}".format(file_info))
    # Generate jpg preview, if needed
    jpg_prev = jpgpreview(file_id, folder_id, main_file_path, logger)
    file_md5 = get_filemd5(main_file_path, logger)
    payload = {'type': 'file',
               'property': 'filemd5',
               'file_id': file_id,
               'api_key': settings.api_key,
               'filetype': filename_suffix,
               'value': file_md5
               }
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    if query_results["result"] is not True:
        query_results = json.loads(r.text.encode('utf-8'))
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        return False
    # Get exif from TIF
    data = get_file_exif(main_file_path)
    data_json = json.loads(data)
    payload = {'type': 'file',
               'property': 'exif',
               'file_id': file_id,
               'api_key': settings.api_key,
               'filetype': filename_suffix.lower(),
               'value': data
               }
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    logger.info("query_results:{}".format(query_results))
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        return False
    # logger.info("file_info: {}".format(file_info))
    # If the file has been checked and passed all, nothing to do and return
    file_checks = 0
    r = requests.post('{}/api/files/{}'.format(settings.api_url, file_id), data=payload_api)
    file_info = json.loads(r.text.encode('utf-8'))
    if len(file_info['file_checks']) == 0:
        file_checks = 1
    else:
        for fcheck in file_info['file_checks']:
            file_checks = file_checks + int(fcheck['check_results'])
    if file_checks == 0:
        # file_updated_at(file_id, db_cursor)
        logger.info("File {} ({}; folder_id: {}) tagged as OK".format(filename_stem, file_id, folder_id))
        return True
    logger.info("Running checks on file {} ({}; folder_id: {})".format(filename_stem, file_id, folder_id))
    # Run each check
    #####################################
    # Add to server side:
    #  - valid_name
    #  - dupe_elsewhere
    #  - md5
    #####################################
    #if 'raw_pair' in settings.project_file_checks:
    if 'raw_pair' in project_checks:
        file_check = 'raw_pair'
        # FilePair check and get MD5 hash
        check_results, check_info, derivative_file = file_pair_check(file_id,
                                     filename,
                                     "{}/{}".format(folder_path, settings.raw_files_path),
                                     'raw_pair')
        payload = {'type': 'file',
                   'property': 'filechecks',
                   'folder_id': folder_id,
                   'file_id': file_id,
                   'api_key': settings.api_key,
                   'file_check': file_check,
                   'value': check_results,
                   'check_info': check_info
                   }
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                          data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            logger.error("769")
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
        file_md5 = get_filemd5("{}/{}/{}".format(folder_path, settings.raw_files_path, derivative_file), logger)
        payload = {'type': 'file',
                   'property': 'filemd5',
                   'file_id': file_id,
                   'api_key': settings.api_key,
                   'filetype': 'raw',
                   'value': file_md5
                   }
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                          data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            logger.error("787")
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
    # if 'jhove' in settings.project_file_checks:
    if 'jhove' in project_checks:
        file_check = 'jhove'
        check_results, check_info = jhove_validate(main_file_path, logger)
        payload = {'type': 'file',
                   'property': 'filechecks',
                   'folder_id': folder_id,
                   'file_id': file_id,
                   'api_key': settings.api_key,
                   'file_check': file_check,
                   'value': check_results,
                   'check_info': check_info
                   }
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                          data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            logger.error("809")
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
    # if 'magick' in settings.project_file_checks:
    if 'magick' in project_checks:
        file_check = 'magick'
        check_results, check_info = magick_validate(file_id, main_file_path, logger)
        payload = {'type': 'file',
                   'property': 'filechecks',
                   'folder_id': folder_id,
                   'file_id': file_id,
                   'api_key': settings.api_key,
                   'file_check': file_check,
                   'value': check_results,
                   'check_info': check_info
                   }
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                          data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            sys.exit(1)
    # if 'tifpages' in settings.project_file_checks:
    if 'tifpages' in project_checks:
        file_check = 'tifpages'
        check_results, check_info = tifpages(main_file_path)
        payload = {'type': 'file',
                   'property': 'filechecks',
                   'folder_id': folder_id,
                   'file_id': file_id,
                   'api_key': settings.api_key,
                   'file_check': file_check,
                   'value': check_results,
                   'check_info': check_info
                   }
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                          data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            logger.error("859")
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
    # if 'tif_compression' in settings.project_file_checks:
    if 'tif_compression' in project_checks:
        file_check = 'tif_compression'
        check_results, check_info = tif_compression(main_file_path)
        payload = {'type': 'file',
                   'property': 'filechecks',
                   'folder_id': folder_id,
                   'file_id': file_id,
                   'api_key': settings.api_key,
                   'file_check': file_check,
                   'value': check_results,
                   'check_info': check_info
                   }
        r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                          data=payload)
        query_results = json.loads(r.text.encode('utf-8'))
        if query_results["result"] is not True:
            logger.error("API Returned Error: {}".format(query_results))
            logger.error("881")
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
    return True
