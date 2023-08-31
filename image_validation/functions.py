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
# from subprocess import PIPE
from pathlib import Path
import shutil
import locale
import itertools

# For MD5
import hashlib

# Parallel
import multiprocessing
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
        if settings.magick is None:
            p = subprocess.Popen(['identify', '-verbose', '-regard-warnings', filename], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env={"MAGICK_THREAD_LIMIT": "1"})
        else:
            p = subprocess.Popen([settings.magick, '-verbose', '-regard-warnings', filename], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env={"MAGICK_THREAD_LIMIT": "1"})
    else:
        if settings.magick is None:
            p = subprocess.Popen(['identify', '-verbose', filename], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env={"MAGICK_THREAD_LIMIT": "1"})
        else:
            p = subprocess.Popen([settings.magick, '-verbose', filename], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env={"MAGICK_THREAD_LIMIT": "1"})
    (out, err) = p.communicate()
    if p.returncode == 0:
        magick_identify = 0
    else:
        magick_identify = 1
        logger.error("magick_out: {} {}".format(file_id, out.decode('UTF-8')))
        logger.error("magick_err: {} {}".format(file_id, err.decode('UTF-8')))
    magick_identify_info = out + err
    check_results = magick_identify
    check_info = magick_identify_info.decode('latin-1')
    return check_results, check_info


def pil_validate(file_id, filename, logger):
    """
    Validate the file with PIL
    """
    # Based on https://opensource.com/article/17/2/python-tricks-artists
    check_results = 0
    check_info = "File {} ({}) is a valid image".format(filename, file_id)
    try:
        im = Image.open(filename)
        im.verify()
    except (IOError, SyntaxError) as e:
        check_results = 1
        check_info = "File is not a valid image"
        logger.error("pil_validate error: {} ({})".format(filename, file_id))
    return check_results, check_info


def check_sequence(filename, folder_info, sequence, sequence_split, logger):
    filename_stem = Path(filename).stem
    logger.info("sequence: {} {}".format(filename, folder_info['folder']))
    logger.info("sequence2: {}".format(folder_info['files']))
    for file in folder_info['files']:
        if file['file_name'] == filename_stem:
            file_id = file['file_id']
            file_info = file
            break
    if file_id is None:
        # Something is wrong
        sys.exit(8)
    file_suffix = filename_stem.split(sequence_split)
    file_wo_suffix = file_suffix[0:len(file_suffix) - 1]
    file_wo_suffix = '_'.join(file_wo_suffix)
    file_suffix = file_suffix[len(file_suffix) - 1]
    # Found last in sequence
    if file_suffix == sequence[len(sequence) - 1]:
        # End of sequence
        check_results = 0
        check_info = "File is the first one in the sequence"
        return (file_id, check_results, check_info)
    for i in range(len(sequence)):
        if file_suffix == sequence[i]:
            next_in_seq = sequence[i + 1]
            next_filename_stem = "{}{}{}".format(file_wo_suffix, sequence_split, next_in_seq)
            for file in folder_info['files']:
                if file['file_name'] == next_filename_stem:
                    check_results = 0
                    check_info = "Next file in sequence ({}) found".format(next_filename_stem)
                    return (file_id, check_results, check_info)
    check_results = 1
    check_info = "File next in sequence ({}) was not found".format(next_filename_stem)
    return (file_id, check_results, check_info)


def sequence_validate(filename, folder_info, logger):
    """
    Validate that a suffix sequence is not missing items
    """
    sequence = settings.sequence
    sequence_split = settings.sequence_split
    file_id, check_results, check_info = check_sequence(filename, folder_info, sequence, sequence_split, logger)
    file_check = 'sequence'
    logger.info("SEQ: results - {} - {}".format(check_results, check_info))
    payload = {'type': 'file',
               'property': 'filechecks',
               'folder_id': folder_info['folder_id'],
               'file_id': file_id,
               'api_key': settings.api_key,
               'file_check': file_check,
               'value': check_results,
               'check_info': check_info
               }
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias), data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        return False
    return True


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


def jpgpreview(file_id, folder_id, file_path, logger):
    """
    Create preview image
    """
    if settings.jpg_previews == "":
        logger.error("JPG preview folder is not set in settings file")
        sys.exit(1)
    if settings.jpg_previews_free != None:
        disk_check = shutil.disk_usage(settings.jpg_previews)
        if (disk_check.free / disk_check.total) < settings.jpg_previews_free:
            logger.error("JPG storage location is running out of space ({}%) - {}".format(
                                                       round(disk_check.free / disk_check.total, 4) * 100,
                                                        settings.jpg_previews))
            sys.exit(1)
    preview_file_path = "{}/folder{}".format(settings.jpg_previews, str(folder_id))
    preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
    preview_image_160 = "{}/160/{}.jpg".format(preview_file_path, file_id)
    preview_image_600 = "{}/600/{}.jpg".format(preview_file_path, file_id)
    preview_image_1200 = "{}/1200/{}.jpg".format(preview_file_path, file_id)
    # Create subfolder if it doesn't exists
    os.makedirs(preview_file_path, exist_ok=True)
    # Other sizes
    for width in [160, 600, 1200]:
        resized_preview_file_path = "{}/{}".format(preview_file_path, width)
        os.makedirs(resized_preview_file_path, exist_ok=True)
    # Check if preview exist
    if os.path.isfile(preview_image) and os.path.isfile(preview_image_1200) and \
        os.path.isfile(preview_image_160) and os.path.isfile(preview_image_600):
        logger.info("Preview images of {} exist".format(file_id))
        return True
    img = Image.open(file_path)
    # if settings.previews_size == "full":
    # Save full size by default
    img.save(preview_image, 'jpeg', icc_profile=img.info.get('icc_profile'))
    if os.path.isfile(preview_image) is False:
        logger.error("File:{}|msg:{}".format(file_path))
        sys.exit(1)
    # 160
    width = 160
    img = Image.open(file_path)
    width_o, height_o = img.size
    height = round(height_o * (width / width_o))
    newsize = (width, height)
    im1 = img.resize(newsize)
    im1.save(preview_image_160, 'jpeg', icc_profile=img.info.get('icc_profile'))
    if os.path.isfile(preview_image_160) is False:
        logger.error("File:{}|msg:{}".format(file_path))
        sys.exit(1)
    # 600
    width = 600
    height = round(height_o * (width / width_o))
    newsize = (width, height)
    im1 = img.resize(newsize)
    im1.save(preview_image_600, 'jpeg', icc_profile=img.info.get('icc_profile'))
    if os.path.isfile(preview_image_600) is False:
        logger.error("File:{}|msg:{}".format(file_path))
        sys.exit(1)
    # 1200
    width = 1200
    height = round(height_o * (width / width_o))
    newsize = (width, height)
    im1 = img.resize(newsize)
    im1.save(preview_image_1200, 'jpeg', icc_profile=img.info.get('icc_profile'))
    if os.path.isfile(preview_image_1200) is False:
        logger.error("File:{}|msg:{}".format(file_path))
        sys.exit(1)
    return


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
    return True


def run_checks_folder_p(project_info, folder_path, logfile_folder, logger):
    """
    Process a folder in parallel
    """
    project_id = project_info['project_alias']
    payload_api = {'api_key': settings.api_key}
    r = requests.post('{}/api/projects/{}'.format(settings.api_url, settings.project_alias), data=payload_api)
    if r.status_code != 200:
        # Something went wrong
        query_results = r.text.encode('utf-8')
        logger.error("API Returned Error: {}".format(query_results))
        sys.exit(1)
    project_info = json.loads(r.text.encode('utf-8'))
    project_checks = project_info['project_checks']
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
    # Check if QC has been run
    r = requests.post('{}/api/folders/{}'.format(settings.api_url, folder_id), data=payload_api)
    if r.status_code != 200:
        # Something went wrong
        logger.error(
            "API ({}) Returned Error: {}".format('{}/api/folders/{}'.format(settings.api_url, folder_id), r.text))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload_api))
        sys.exit(9)
    folder_info = json.loads(r.text.encode('utf-8'))
    if folder_info['qc_status'] != "QC Pending":
        # QC done, so skip
        logger.info("Folder QC has been completed, skipping {}".format(folder_path))
        return folder_id
    # Tag folder as under verification
    payload = {'type': 'folder',
               'folder_id': folder_id,
               'api_key': settings.api_key,
               'property': 'checking_folder',
               'value': 1
               }
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        sys.exit(1)
    # Check if MD5 exists in tif folder
    if len(glob.glob(folder_path + "/" + settings.main_files_path + "/*.md5")) == 1:
        md5_exists = 0
    else:
        md5_exists = 1
    payload = {'type': 'folder',
               'folder_id': folder_id,
               'api_key': settings.api_key,
               'property': 'tif_md5_exists',
               'value': md5_exists
               }
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        sys.exit(1)
    # Check if MD5 exists in raw folder
    if len(glob.glob(folder_path + "/" + settings.raw_files_path + "/*.md5")) == 1:
        md5_raw_exists = 0
    else:
        md5_raw_exists = 1
    payload = {'type': 'folder',
               'folder_id': folder_id,
               'api_key': settings.api_key,
               'property': 'raw_md5_exists',
               'value': md5_raw_exists
               }
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        sys.exit(1)
    if settings.md5_required:
        if md5_exists == 1 or md5_raw_exists == 1:
            # Folder is missing md5 files
            logger.info("Folder {} is missing md5 files".format(folder_path))
            # Update folder stats
            update_folder_stats(folder_id, folder_path, logger)
            return folder_id
    payload = {'type': 'folder', 'folder_id': folder_id, 'api_key': settings.api_key, 'property': 'status0',
               'value': ''}
    r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias),
                      data=payload)
    query_results = json.loads(r.text.encode('utf-8'))
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
        folder_full_path_files = [file for file in folder_full_path_files if Path(file).suffix != '.md5']
        folder_raw_path = "{}/{}".format(folder_path, settings.raw_files_path)
        folder_raw_path_files = glob.glob("{}/*".format(folder_raw_path))
        folder_raw_path_files = [file for file in folder_raw_path_files if Path(file).suffix != '.md5']
        if len(folder_full_path_files) != len(folder_raw_path_files):
            folder_status_msg = "No. of files do not match (main: {}, raws: {})".format(len(folder_full_path_files), len(folder_raw_path_files))
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
        else:
            payload = {'type': 'folder', 'folder_id': folder_id, 'api_key': settings.api_key, 'property': 'status0',
                       'value': ""}
            r = requests.post('{}/api/update/{}'.format(settings.api_url, settings.project_alias), data=payload)
            query_results = json.loads(r.text.encode('utf-8'))
            if query_results["result"] is not True:
                logger.error("API Returned Error: {}".format(query_results))
                logger.error("Request: {}".format(str(r.request)))
                logger.error("Headers: {}".format(r.headers))
                logger.error("Payload: {}".format(payload))
                sys.exit(1)
        # Get all files in the folder
        files = glob.glob("{}/*.*".format(folder_full_path))
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
            print_str = "Started run of {notasks} tasks for {folder_path}"
            print_str = print_str.format(notasks=str(locale.format_string("%d", no_tasks, grouping=True)), folder_path=folder_path)
            logger.info(print_str)
            # Process files in parallel
            for file in files:
                process_image_p(file, folder_path, folder_id, project_id, logfile_folder)
        else:
            print_str = "Started parallel run of {notasks} tasks on {workers} workers for {folder_path}"
            print_str = print_str.format(notasks=str(locale.format_string("%d", no_tasks, grouping=True)), workers=str(
                settings.no_workers), folder_path=folder_path)
            logger.info(print_str)
            # Process files in parallel
            inputs = zip(files, itertools.repeat(folder_path), itertools.repeat(folder_id), itertools.repeat(project_id), itertools.repeat(logfile_folder))
            with Pool(settings.no_workers) as pool:
                pool.starmap(process_image_p, inputs)
                pool.close()
                pool.join()
    # Run end-of-folder checks
    if 'sequence' in project_checks:
        no_tasks = len(files)
        r = requests.post('{}/api/folders/{}'.format(settings.api_url, folder_id), data=payload_api)
        if r.status_code != 200:
            # Something went wrong
            logger.error(
                "API ({}) Returned Error: {}".format('{}/api/folders/{}'.format(settings.api_url, folder_id), r.text))
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload_api))
            sys.exit(9)
        folder_info = json.loads(r.text.encode('utf-8'))
        if settings.no_workers == 1:
            print_str = "Started run of {notasks} tasks for 'sequence'"
            print_str = print_str.format(notasks=str(locale.format_string("%d", no_tasks, grouping=True)))
            logger.info(print_str)
            # Process files in parallel
            for file in files:
                sequence_validate(file, folder_info, logger)
        else:
            print_str = "Started parallel run of {notasks} tasks on {workers} workers for 'sequence'"
            print_str = print_str.format(notasks=str(locale.format_string("%d", no_tasks, grouping=True)), workers=str(
                settings.no_workers))
            logger.info(print_str)
            # Process files in parallel
            inputs = zip(files, itertools.repeat(folder_info), itertools.repeat(logger))
            with Pool(settings.no_workers) as pool:
                pool.starmap(sequence_validate, inputs)
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
    import subprocess
    import requests
    random_int = random.randint(1, 1000)
    # Logging
    current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    logfile = '{}/{}_{}.log'.format(logfile_folder, current_time, random_int)
    logging.basicConfig(filename=logfile, filemode='a', level=logging.DEBUG,
                        format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
                        datefmt='%y-%b-%d %H:%M:%S')
    logger = logging.getLogger("osprey_{}".format(random_int))
    # main_file_path = "{}/{}/{}".format(folder_path, settings.main_files_path, filename)
    main_file_path = filename
    logger.info("filename: {}".format(main_file_path))
    folder_id = int(folder_id)
    filename_stem = Path(filename).stem
    filename_suffix = Path(filename).suffix[1:]
    file_name = Path(filename).name
    payload_api = {'api_key': settings.api_key}
    # s = requests.Session()
    r = requests.post('{}/api/folders/{}'.format(settings.api_url, folder_id), data=payload_api)
    if r.status_code != 200:
        # Something went wrong
        logger.error("API ({}) Returned Error: {}".format('{}/api/folders/{}'.format(settings.api_url, folder_id), r.text))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload_api))
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
    logger.info("project_checks: {}".format(project_checks))
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
        # Get filesize from TIF:
        logging.debug("file_size_pre: {}".format(main_file_path))
        file_size = os.path.getsize(main_file_path)
        logging.debug("file_size: {} {}".format(main_file_path, file_size))
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
        # logger.info("folder_info:{}".format(folder_info))
        for file in folder_info['files']:
            if file['file_name'] == filename_stem:
                file_id = file['file_id']
                file_info = file
                break
    logging.debug("file_info: {} - {}".format(file_id, file_info))
    # Generate jpg preview, if needed
    jpg_prev = jpgpreview(file_id, folder_id, main_file_path, logger)
    logger.info("jpg_prev: {} {} {}".format(file_id, main_file_path, jpg_prev))
    logger.info("file_md5_pre: {} {}".format(file_id, main_file_path))
    file_md5 = get_filemd5(main_file_path, logger)
    logger.info("file_md5: {} {} - {}".format(file_id, main_file_path, file_md5))
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
    logger.info("file_exif_pre: {}".format(main_file_path))
    data = get_file_exif(main_file_path)
    logger.info("file_exif: {}".format(main_file_path))
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
    if query_results["result"] is not True:
        logger.error("API Returned Error: {}".format(query_results))
        logger.error("Request: {}".format(str(r.request)))
        logger.error("Headers: {}".format(r.headers))
        logger.error("Payload: {}".format(payload))
        return False
    logger.info("Running checks on file {} ({}; folder_id: {})".format(filename_stem, file_id, folder_id))
    # Run each check
    if 'raw_pair' in project_checks:
        file_check = 'raw_pair'
        # FilePair check and get MD5 hash
        logger.info("raw_pair_pre: {} {}".format(file_id, file_name))
        check_results, check_info, raw_file = file_pair_check(file_id,
                                     file_name,
                                     "{}/{}".format(folder_path, settings.raw_files_path),
                                     'raw_pair')
        logger.info("raw_pair: {} {} {} {}".format(file_id, file_name, check_results, check_info))
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
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
        if check_results == 0:
            logger.info("file_raw_md5_pre: {} {}".format(file_id, raw_file))
            file_md5 = get_filemd5(raw_file, logger)
            logger.info("file_raw_md5: {} {} - {}".format(file_id, raw_file, file_md5))
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
                logger.error("Request: {}".format(str(r.request)))
                logger.error("Headers: {}".format(r.headers))
                logger.error("Payload: {}".format(payload))
                return False
    if 'jhove' in project_checks:
        file_check = 'jhove'
        logger.info("jhove_validate_pre: {} {}".format(file_id, main_file_path))
        check_results, check_info = jhove_validate(main_file_path, logger)
        logger.info("jhove_validate: {} {} {}".format(file_id, check_results, check_info))
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
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
    if 'tifpages' in project_checks:
        file_check = 'tifpages'
        logger.info("tifpages_pre: {} {}".format(file_id, main_file_path))
        check_results, check_info = tifpages(main_file_path)
        logger.info("tifpages: {} {} {}".format(file_id, check_results, check_info))
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
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
    if 'magick' in project_checks:
        file_check = 'magick'
        logger.info("magick_validate_pre: {} {}".format(file_id, main_file_path))
        check_results, check_info = magick_validate(file_id, main_file_path, logger)
        logger.info("magick_validate: {} {} {}".format(file_id, check_results, check_info))
        if check_results != 0:
            logger.error("magick error: {}".format(check_info))
            sys.exit(1)
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
    if 'tif_compression' in project_checks:
        file_check = 'tif_compression'
        logger.info("tif_compression_pre: {} {}".format(file_id, main_file_path))
        check_results, check_info = tif_compression(main_file_path)
        logger.info("tif_compression: {} {} {}".format(file_id, check_results, check_info))
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
            logger.error("Request: {}".format(str(r.request)))
            logger.error("Headers: {}".format(r.headers))
            logger.error("Payload: {}".format(payload))
            return False
    return True
