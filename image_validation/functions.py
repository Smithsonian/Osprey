# Functions for osprey.py
from datetime import datetime
import os
import subprocess
import re
import xmltodict
import sys
import settings
from random import randint
import queries
# For MD5
import hashlib
import glob
from PIL import Image
from subprocess import PIPE
from pathlib import Path
import shutil
import locale

# For Postgres
import psycopg2

# Parallel
import itertools
from multiprocessing import Pool


def check_requirements(program):
    """
    Check if required programs are installed
    """
    # From https://stackoverflow.com/a/34177358
    from shutil import which
    return which(program) is not None


def compress_log(filecheck_dir, log_folder):
    """
    Compress log files
    """
    os.chdir(log_folder)
    for file in glob.glob('*.log'):
        subprocess.run(["zip", "{}.zip".format(file), file])
        os.remove(file)
    os.chdir(filecheck_dir)
    return True


def check_folder(folder_name, folder_path, project_id, db_cursor):
    """
    Check if a folder exists, add if it does not
    """
    db_cursor.execute(queries.select_folderid,
                      {'project_folder': folder_name, 'folder_path': folder_path, 'project_id': project_id})
    folder_id = db_cursor.fetchone()
    if folder_id is None:
        # Folder does not exists, create
        db_cursor.execute(queries.new_folder,
                          {'project_folder': folder_name, 'folder_path': folder_path, 'project_id': project_id})
        folder_id = db_cursor.fetchone()
    folder_date = settings.folder_date(folder_name)
    db_cursor.execute(queries.folder_date, {'datequery': folder_date, 'folder_id': folder_id[0]})
    return folder_id[0]


def folder_updated_at(folder_id, db_cursor):
    """
    Update the last time the folder was checked
    """
    db_cursor.execute(queries.folder_updated_at, {'folder_id': folder_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def file_updated_at(file_id, db_cursor):
    """
    Update the last time the file was checked
    """
    db_cursor.execute(queries.file_updated_at, {'file_id': file_id})
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'file_updated_at',
                                           'log_text': db_cursor.query.decode("utf-8")})
    return True


def jhove_validate(file_id, filename, db_cursor):
    """
    Validate the file with JHOVE
    """
    # Where to write the results
    xml_file = "{}/jhove_{}_{}.xml".format(settings.tmp_folder, file_id, randint(100, 100000))
    if os.path.isfile(xml_file):
        os.unlink(xml_file)
    # Run JHOVE
    subprocess.run([settings.jhove_path, "-h", "xml", "-o", xml_file, filename])
    # Open and read the results xml
    try:
        with open(xml_file) as fd:
            doc = xmltodict.parse(fd.read())
    except Exception as e:
        error_msg = "Could not find result file from JHOVE ({}) ({})".format(xml_file, e)
        db_cursor.execute(queries.file_check,
                          {'file_id': file_id, 'file_check': 'jhove', 'check_results': 9, 'check_info': error_msg})
        return False
    if os.path.isfile(xml_file):
        os.unlink(xml_file)
    # Get file status
    file_status = doc['jhove']['repInfo']['status']
    if file_status == "Well-Formed and valid":
        jhove_val = 0
    else:
        jhove_val = 1
        if len(doc['jhove']['repInfo']['messages']) == 1:
            # If the only error is with the WhiteBalance, ignore
            # Issue open at Github, seems will be fixed in future release
            # https://github.com/openpreserve/jhove/issues/364
            if doc['jhove']['repInfo']['messages']['message']['#text'][:31] == "WhiteBalance value out of range":
                jhove_val = 0
        file_status = doc['jhove']['repInfo']['messages']['message']['#text']
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'jhove', 'check_results': jhove_val,
                                           'check_info': file_status})
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'jhove_validate',
                                           'log_text': db_cursor.query.decode("utf-8")})
    return True


def magick_validate(file_id, filename, db_cursor, paranoid=False):
    """
    Validate the file with Imagemagick
    """
    if paranoid:
        p = subprocess.Popen(['identify', '-verbose', '-regard-warnings', filename], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    else:
        p = subprocess.Popen(['identify', '-verbose', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    if p.returncode == 0:
        magick_identify = 0
    else:
        magick_identify = 1
    magick_identify_info = out + err
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'magick', 'check_results': magick_identify,
                                           'check_info': magick_identify_info.decode('latin-1')})
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'magick_validate',
                                           'log_text': db_cursor.query.decode("utf-8")})
    return True


def tif_compression(file_id, filename, db_cursor):
    """
    Check if the image has LZW compression
    """
    p = subprocess.Popen(['exiftool', '-T', '-compression', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    compressed_info = out.decode('UTF-8').replace('\n', '')
    if compressed_info == "LZW":
        f_compressed = 0
    else:
        f_compressed = 1
    db_cursor.execute(queries.file_check,
                      {'file_id': file_id, 'file_check': 'tif_compression', 'check_results': f_compressed,
                       'check_info': compressed_info})
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'tif_compression',
                                           'log_text': db_cursor.query.decode("utf-8")})
    return True


def valid_name(file_id, filename, db_cursor):
    """
    Check if filename in database of accepted names
    """
    db_cursor.execute(settings.filename_pattern_query.format(Path(filename).stem))
    valid_names = db_cursor.fetchone()[0]
    if valid_names == 0:
        filename_check = 1
        filename_check_info = "Filename {} not in list".format(Path(filename).stem)
    else:
        filename_check = 0
        filename_check_info = "Filename {} in list".format(Path(filename).stem)
    db_cursor.execute(queries.file_check,
                      {'file_id': file_id, 'file_check': 'valid_name', 'check_results': filename_check,
                       'check_info': filename_check_info})
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'valid_name',
                                           'log_text': db_cursor.query.decode("utf-8")})
    return True


def tifpages(file_id, filename, db_cursor):
    """
    Check if TIF has multiple pages
    """
    p = subprocess.Popen(['identify', '-format', '%n\\n', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    try:
        if int(len(out.split())) == 1:
            pages_vals = 0
            no_pages = str(int(len(out.split()))) + " page"
        else:
            pages_vals = 1
            no_pages = str(int(len(out.split()))) + " pages"
    except Exception as e:
        no_pages = "Unknown ({})".format(e)
        pages_vals = 1
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'tifpages', 'check_results': pages_vals,
                                           'check_info': no_pages})
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'tifpages',
                                           'log_text': db_cursor.query.decode("utf-8")})
    return True


def file_exif(file_id, filename, filetype, db_cursor):
    """
    Extract the EXIF info from the RAW file
    """
    p = subprocess.Popen(['exiftool', '-t', '-a', '-U', '-u', '-D', '-G1', '-s', filename], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    exif_info = out
    for line in exif_info.splitlines():
        # Non utf, ignore for now
        try:
            tag = re.split(r'\t+', line.decode('UTF-8'))
            db_cursor.execute(queries.save_exif,
                              {'file_id': file_id, 'filetype': filetype, 'taggroup': tag[0], 'tagid': tag[1],
                               'tag': tag[2], 'value': tag[3]})
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'file_exif',
                                                   'log_text': db_cursor.query.decode("utf-8")})
        except Exception as e:
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'file_exif',
                                                   'log_text': "Tag not in utf-8 for file {}, {} {} {} ({})".format(file_id, tag[0], tag[1], tag[2], e)})
            continue
    return True


def filemd5(filepath):
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


def file_pair_check(file_id, filename, derivative_path, derivative_type, db_cursor):
    """
    Check if a file has a pair (main + raw)
    """
    file_stem = Path(filename).stem
    # Check if file pair is present
    os.chdir(derivative_path)
    derivative_file = glob.glob("{}.*".format(file_stem))[0]
    if os.path.isfile(derivative_file) is False:
        # Raw file is missing
        file_pair = 1
        file_pair_info = "Missing derivative file"
    else:
        file_pair = 0
        file_pair_info = "Derivative file {} found (file_id: {})".format(derivative_file, file_id)
    db_cursor.execute(queries.file_check,
                      {'file_id': file_id, 'file_check': derivative_type, 'check_results': file_pair,
                       'check_info': file_pair_info})
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'file_pair_check',
                                           'log_text': db_cursor.query.decode("utf-8")})
    return derivative_file



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


def check_stitched_jpg(file_id, filename, db_cursor):
    """
    Run checks for jpg files that were stitched from 2 images
    """
    p = subprocess.Popen(['identify', '-verbose', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    if p.returncode == 0:
        magick_identify = 0
        magick_identify_info = out
        magick_return = True
    else:
        magick_identify = 1
        magick_identify_info = err
        magick_return = False
    db_cursor.execute(queries.file_check,
                      {'file_id': file_id, 'file_check': 'stitched_jpg', 'check_results': magick_identify,
                       'check_info': magick_identify_info.decode("utf-8").replace("'", "''")})
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'check_stitched_jpg',
                                           'log_text': db_cursor.query.decode("utf-8")})
    if magick_return:
        # Store MD5
        file_md5 = filemd5(filename)
        db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'jpg', 'md5': file_md5})
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'check_stitched_jpg',
                                               'log_text': db_cursor.query.decode("utf-8")})
    return True


def jpgpreview(file_id, folder_id, filename, db_cursor):
    """
    Create preview image
    """
    if settings.jpg_previews == "":
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'jpgpreview',
                                               'log_text': "JPG preview folder is not set in settings file"})
        sys.exit(1)
    disk_check = shutil.disk_usage(settings.jpg_previews)
    if (disk_check.free / disk_check.total) < 0.1:
        # logger.error("JPG storage location is running out of space ({}%) - {}".format(
        #     round(disk_check.free / disk_check.total, 4) * 100, settings.jpg_previews))
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'jpgpreview',
                                               'log_text': "JPG storage location is running out of space ({}%) - {}".format(
            round(disk_check.free / disk_check.total, 4) * 100, settings.jpg_previews)})
        sys.exit(1)
    preview_file_path = "{}/folder{}".format(settings.jpg_previews, str(folder_id))
    preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
    # Create subfolder if it doesn't exists
    if not os.path.exists(preview_file_path):
        os.makedirs(preview_file_path)
    # Delete old image, if exists
    if os.path.isfile(preview_image):
        im = Image.open(filename)
        width, height = im.size
        if width != settings.previews_size and height != settings.previews_size:
            # Size in settings changed, create new image
            os.remove(preview_image)
        else:
            # logger.info("JPG preview {} exists".format(preview_image))
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'jpgpreview',
                                                   'log_text': "JPG preview {} exists".format(preview_image)})
            return True
    #logger.info("Creating preview_image:{}".format(preview_image))
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'jpgpreview',
                                           'log_text': "Creating preview_image:{}".format(preview_image)})
    if settings.previews_size == "full":
        p = subprocess.Popen(['convert', '-quiet', '{}'.format(filename), preview_image], stdout=PIPE, stderr=PIPE)
    else:
        p = subprocess.Popen(['convert', '-quiet', '{}'.format(filename), '-resize',
                              '{imgsize}x{imgsize}'.format(imgsize=settings.previews_size),
                              preview_image], stdout=PIPE, stderr=PIPE)
    out = p.communicate()
    if os.path.isfile(preview_image):
        # logger.info(out)
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'jpgpreview',
                                               'log_text': out})
        return True
    else:
        # logger.error("File:{}|msg:{}".format(filename, out))
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'jpgpreview',
                                               'log_text': "File:{}|msg:{}".format(filename, out)})
        return False


def update_folder_stats(folder_id, db_cursor, logger):
    """
    Update the stats for the folder
    """
    db_cursor.execute(queries.update_nofiles, {'folder_id': folder_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    db_cursor.execute(queries.get_fileserrors, {'folder_id': folder_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    no_errors = db_cursor.fetchone()[0]
    db_cursor.execute(queries.get_filespending, {'folder_id': folder_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    no_pending = db_cursor.fetchone()[0]
    if no_errors > 0:
        f_errors = 1
    else:
        if no_pending > 0:
            f_errors = 9
        else:
            f_errors = 0
    db_cursor.execute(queries.update_folder_errors, {'folder_id': folder_id, 'f_errors': f_errors})
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def process_image(filename, folder_path, folder_id):
    """
    Run checks for image files
    """
    folder_id = int(folder_id)
    filename_stem = Path(filename).stem
    filename_suffix = Path(filename).suffix[1:]
    # Connect to database
    conn = psycopg2.connect(host=settings.db_host, database=settings.db_db, user=settings.db_user,
                            password=settings.db_password, connect_timeout=60)
    conn.autocommit = True
    db_cursor = conn.cursor()
    # Check if file exists, insert if not
    db_cursor.execute(queries.select_file_id, {'file_name': filename_stem, 'folder_id': folder_id})
    file_id = db_cursor.fetchone()
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'process_image',
                                           'log_text': db_cursor.query.decode("utf-8")})
    if file_id is None:
        # Get modified date for file
        file_timestamp_float = os.path.getmtime("{}/{}/{}".format(folder_path, settings.main_files_path, filename))
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        db_cursor.execute(queries.insert_file,
                          {'file_name': filename_stem, 'folder_id': folder_id, 'file_timestamp': file_timestamp})
        file_id = db_cursor.fetchone()[0]
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'process_image',
                                               'log_text': db_cursor.query.decode("utf-8")})
    else:
        file_id = file_id[0]
    # Check if file is OK
    file_checks = 0
    for filecheck in settings.project_file_checks:
        db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': filecheck})
        result = db_cursor.fetchone()
        if result is None:
            db_cursor.execute(queries.file_check,
                              {'file_id': file_id, 'file_check': filecheck, 'check_results': 9, 'check_info': ''})
            result = 1
        else:
            result = result[0]
            if result == 9:
                result = 1
        file_checks = file_checks + result
    # Check if JPG preview exists
    preview_file_path = "{}/folder{}".format(settings.jpg_previews, str(folder_id))
    preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
    if os.path.isfile(preview_image) is False:
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'process_image',
                                               'log_text': "jpg_preview {} does not exist for file_id:{}".format(preview_image, file_id)})
        file_checks = file_checks + 1
    # Get filesize from TIF:
    file_size = os.path.getsize("{}/{}/{}".format(folder_path, settings.main_files_path, filename))
    db_cursor.execute(queries.save_filesize, {'file_id': file_id, 'filetype': filename_suffix.lower(), 'filesize':
        file_size})
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'process_image',
                                           'log_text': db_cursor.query.decode("utf-8")})
    # Get exif from TIF
    db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': filename_suffix.lower()})
    check_exif = db_cursor.fetchone()[0]
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'process_image',
                                           'log_text': "check_exif_tif: {}".format(check_exif)})
    if check_exif == 0:
        file_checks = file_checks + 1
    # Check if MD5 is stored
    db_cursor.execute(queries.select_file_md5, {'file_id': file_id, 'filetype': filename_suffix.lower()})
    result = db_cursor.fetchone()
    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'process_image',
                                           'log_text': db_cursor.query.decode("utf-8")})
    if result is None:
        file_checks = file_checks + 1
    if file_checks == 0:
        file_updated_at(file_id, db_cursor)
        # Disconnect from db
        conn.close()
        return True
    else:
        # Checks that do not need a local copy
        if 'raw_pair' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'raw_pair'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                # FilePair check
                pair_check = file_pair_check(file_id, filename, "{}/{}".format(folder_path, settings.raw_files_path),
                                             'raw_pair', db_cursor)
                file_md5 = filemd5("{}/{}/{}".format(folder_path, settings.raw_files_path, pair_check))
                db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'raw', 'md5': file_md5})
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text': db_cursor.query.decode("utf-8")})
                file_checks = file_checks - 1
        if file_checks == 0:
            # Disconnect from db
            conn.close()
            return True
        if 'valid_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'valid_name'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                # valid name in file
                valid_name(file_id, filename_stem, db_cursor)
                file_checks = file_checks - 1
        if file_checks == 0:
            # Disconnect from db
            conn.close()
            return True
        if 'unique_file' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'unique_file'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                # Check in project
                db_cursor.execute(queries.check_unique, {'file_name': filename_stem, 'folder_id': folder_id,
                                                         'project_id': settings.project_id, 'file_id': file_id})
                result = db_cursor.fetchall()
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text': db_cursor.query.decode("utf-8")})
                if len(result) == 0:
                    unique_file = 0
                    db_cursor.execute(queries.file_check,
                                      {'file_id': file_id, 'file_check': 'unique_file', 'check_results': unique_file,
                                       'check_info': ""})
                    db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                           'log_area': 'process_image',
                                                           'log_text': db_cursor.query.decode("utf-8")})
                    file_checks = file_checks - 1
                else:
                    unique_file = 1
                    for dupe in result:
                        db_cursor.execute(queries.not_unique, {'folder_id': dupe[1]})
                        folder_dupe = db_cursor.fetchone()
                        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                               'log_area': 'process_image',
                                                               'log_text': db_cursor.query.decode("utf-8")})
                        db_cursor.execute(queries.file_check,
                                          {'file_id': dupe[0], 'file_check': 'unique_file', 'check_results': 1,
                                           'check_info': "File with same name in {}".format(folder_path)})
                        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                               'log_area': 'process_image',
                                                               'log_text': db_cursor.query.decode("utf-8")})
                        db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'unique_file',
                                                               'check_results': unique_file,
                                                               'check_info': "File with same name in {}".format(
                                                                   folder_dupe[0])})
                        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                               'log_area': 'process_image',
                                                               'log_text': db_cursor.query.decode("utf-8")})
        if file_checks == 0:
            # Disconnect from db
            conn.close()
            return True
        if 'old_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                db_cursor.execute(queries.check_unique_old, {'file_name': filename_stem, 'folder_id': folder_id,
                                                             'project_id': settings.project_id})
                result = db_cursor.fetchall()
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text': db_cursor.query.decode("utf-8")})
                if len(result) > 0:
                    old_name = 1
                    folders = ",".join(result[0])
                else:
                    old_name = 0
                    folders = ""
                db_cursor.execute(queries.file_check,
                                  {'file_id': file_id, 'file_check': 'old_name', 'check_results': old_name,
                                   'check_info': folders})
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text': db_cursor.query.decode("utf-8")})
                file_checks = file_checks - 1
        if 'prefix' in settings.project_file_checks:
            if settings.filename_prefix is None:
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text': "The settings file specified to check the prefix of filenames, but the prefix to use is empty."})
                sys.exit(1)
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'prefix'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                if filename_stem.startswith(settings.filename_prefix):
                    prefix_res = 0
                    prefix_info = ""
                else:
                    prefix_res = db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                           'log_area': 'process_image',
                                           'log_text': db_cursor.query.decode("utf-8")})
                    prefix_info = "Filename '{}' does not match required prefix '{}'".format(filename_stem,
                                                                                             settings.filename_prefix)
                db_cursor.execute(queries.file_check,
                                  {'file_id': file_id, 'file_check': 'prefix', 'check_results': prefix_res,
                                   'check_info': prefix_info})
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text': db_cursor.query.decode("utf-8")})
                file_checks = file_checks - 1
        if 'suffix' in settings.project_file_checks:
            if settings.filename_prefix is None:
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text': "The settings file specified to check the suffix of filenames, but the suffix to use is empty."})
                sys.exit(1)
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'suffix'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                if filename_stem.endswith(settings.filename_suffix):
                    prefix_res = 0
                    prefix_info = ""
                else:
                    prefix_res = 1
                    prefix_info = "Filename '{}' does not match required prefix '{}'".format(filename_stem,
                                                                                             settings.filename_suffix)
                db_cursor.execute(queries.file_check,
                                  {'file_id': file_id, 'file_check': 'suffix', 'check_results': prefix_res,
                                   'check_info': prefix_info})
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text': db_cursor.query.decode("utf-8")})
                file_checks = file_checks - 1
        if file_checks == 0:
            # Disconnect from db
            conn.close()
            return True
        # Checks that DO need a local copy
        # Check if there is enough space first
        local_disk = shutil.disk_usage(settings.tmp_folder)
        if local_disk.free / local_disk.total < 0.1:
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': "Disk is running out of space ({}%) - {}".format(round(local_disk.free / local_disk.total, 4) * 100,
                                                                 settings.tmp_folder)})
            sys.exit(1)
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'process_image',
                                               'log_text': "file_checks: {}".format(file_checks)})
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'process_image',
                                               'log_text': "Copying file {} to local tmp".format(filename)})
        # Copy file to tmp folder
        # Create folder in tmp
        tmp_folder = "{}/{}".format(settings.tmp_folder, randint(100, 1000000))
        if os.path.isdir(tmp_folder):
            tmp_folder = "{}/{}".format(settings.tmp_folder, randint(100, 1000000))
        os.makedirs(tmp_folder)
        local_tempfile = "{}/{}".format(tmp_folder, filename)
        # Check if file already exists
        if os.path.isfile(local_tempfile):
            os.remove(local_tempfile)
        try:
            shutil.copyfile("{}/{}/{}".format(folder_path, settings.main_files_path, filename), local_tempfile)
        except Exception as e:
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': "Could not copy file {}/{}/{} to local tmp ({})".format(folder_path,
                                                                        settings.main_files_path,
                                                                        filename,
                                                                        e)})
            db_cursor.execute(queries.file_exists, {'file_exists': 1, 'file_id': file_id})
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            # Serious enough error, quit
            sys.exit(1)
        # Generate jpg preview, if needed
        jpg_prev = jpgpreview(file_id, folder_id, local_tempfile, db_cursor)
        # Compare MD5 between source and copy
        db_cursor.execute(queries.select_file_md5, {'file_id': file_id, 'filetype': filename_suffix})
        result = db_cursor.fetchone()
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'process_image',
                                               'log_text': db_cursor.query.decode("utf-8")})
        if result is None:
            sourcefile_md5 = filemd5("{}/{}/{}".format(folder_path, settings.main_files_path, filename))
            # Store MD5
            file_md5 = filemd5(local_tempfile)
            if sourcefile_md5 != file_md5:
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text':
                    "MD5 hash of local copy does not match the source: {} vs {}".format(sourcefile_md5, file_md5)})
                # Serious enough error, quit
                sys.exit(1)
            db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': filename_suffix, 'md5': file_md5})
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': "{}_md5:{}".format(filename_suffix, file_md5)})
        if 'jhove' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'jhove'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                # JHOVE check
                jhove_validate(file_id, local_tempfile, db_cursor)
        if 'magick' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'magick'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                # Imagemagick check
                magick_validate(file_id, local_tempfile, db_cursor)
        if 'stitched_jpg' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'stitched_jpg'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                # JPG check
                stitched_name = filename_stem.replace(settings.jpgstitch_original_1, settings.jpgstitch_new)
                stitched_name = stitched_name.replace(settings.jpgstitch_original_2, settings.jpgstitch_new)
                check_stitched_jpg(file_id, "{}/{}/{}.jpg".format(folder_path, settings.jpg_files_path, stitched_name),
                                   db_cursor)
        if 'tifpages' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tifpages'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                # check if tif has multiple pages
                tifpages(file_id, local_tempfile, db_cursor)
        if 'tif_compression' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tif_compression'})
            result = db_cursor.fetchone()[0]
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': db_cursor.query.decode("utf-8")})
            if result != 0:
                # check if tif is compressed
                tif_compression(file_id, local_tempfile, db_cursor)
        # Get exif from TIF
        db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': filename_suffix.lower()})
        check_exif = db_cursor.fetchone()[0]
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'process_image',
                                               'log_text': "check_exif_tif: {}".format(check_exif)})
        if check_exif == 0:
            db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                   'log_area': 'process_image',
                                                   'log_text': "Getting EXIF from {}/{}/{}".format(folder_path, settings.main_files_path, filename)})
            file_exif(file_id, local_tempfile, filename_suffix.lower(), db_cursor)
        # Get exif from RAW
        db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': 'raw'})
        check_exif = db_cursor.fetchone()[0]
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'process_image',
                                               'log_text': "check_exif_raw: {}".format(check_exif)})
        if check_exif == 0:
            pair_file = file_pair_check(file_id, filename, "{}/{}".format(folder_path, settings.raw_files_path),
                                         'raw_pair', db_cursor)
            if os.path.isfile(
                    "{}/{}/{}".format(folder_path, settings.raw_files_path, pair_file)):
                db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                                       'log_area': 'process_image',
                                                       'log_text': "Getting EXIF from {}/{}/{}".format(folder_path, settings.raw_files_path,
                                                           pair_file)})
                file_exif(file_id,
                          "{}/{}/{}".format(folder_path,
                                               settings.raw_files_path,
                                               pair_file),
                          'raw',
                          db_cursor)
        db_cursor.execute(queries.insert_log, {'project_id': settings.project_id, 'file_id': file_id,
                                               'log_area': 'process_image',
                                               'log_text': "jpg_prev:{}".format(jpg_prev)})
        if os.path.isfile(local_tempfile):
            os.remove(local_tempfile)
        file_updated_at(file_id, db_cursor)
        shutil.rmtree(tmp_folder, ignore_errors=True)
        # Disconnect from db
        conn.close()
        return True


def run_checks_folder(project_id, folder_path, db_cursor, logger):
    """
    Process a folder
    """
    logger.info("Processing folder: {}".format(folder_path))
    folder_name = os.path.basename(folder_path)
    # Check if the folder exists in the database
    folder_id = check_folder(folder_name, folder_path, project_id, db_cursor)
    if folder_id is None:
        logger.error("Folder {} had an error".format(folder_name))
        return None
    # Check if folder is ready or in DAMS
    db_cursor.execute(queries.folder_in_dams, {'folder_id': folder_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    f_in_dams = db_cursor.fetchone()
    if f_in_dams[0] == 0:
        # Folder ready for DAMS, skip
        logger.info("Folder ready for DAMS, skipping {}".format(folder_path))
        return folder_id
    elif f_in_dams[0] == 1:
        # Folder in DAMS already, skip
        logger.info("Folder in DAMS, skipping {}".format(folder_path))
        return folder_id
    # Reset folder error information
    db_cursor.execute(queries.update_folder_0, {'folder_id': folder_id})
    if os.path.isdir("{}/{}".format(folder_path, settings.main_files_path)) is False:
        logger.info("Missing MAIN folder in {}".format(folder_path))
        db_cursor.execute(queries.update_folder_status9,
                          {'error_info': "Missing MAIN folder", 'folder_id': folder_id})
        logger.debug(db_cursor.query.decode("utf-8"))
        db_cursor.execute(queries.del_folder_files, {'folder_id': folder_id})
        logger.debug(db_cursor.query.decode("utf-8"))
        return folder_id
    else:
        logger.info("MAIN folder found in {}".format(folder_path))
        folder_full_path = "{}/{}".format(folder_path, settings.main_files_path)
        os.chdir(folder_full_path)
        # Get all files in the folder
        files = glob.glob("*.*")
        # Remove md5 files from list
        files = [file for file in files if Path(file).suffix != '.md5']
        ###############
        # Parallel
        ###############
        no_tasks = len(files)
        print_str = "Started parallel run of {notasks} tasks on {workers} workers"
        print_str = print_str.format(notasks=str(locale.format_string("%d", no_tasks, grouping=True)), workers=str(
            settings.no_workers))
        logger.info(print_str)
        # Start timer
        with Pool() as pool:
            pool.starmap(process_image, zip(files,
                                            itertools.repeat(folder_path),
                                            itertools.repeat(folder_id)))
        ###############
        # for file in files:
        #     logger.info("Running checks on file {}".format(file))
        #     # process_image(file, folder_path, folder_id, db_cursor, logger)
        #     process_image(file, folder_path, folder_id)
    folder_updated_at(folder_id, db_cursor)
    # Update folder stats
    update_folder_stats(folder_id, db_cursor, logger)
    logger.debug(db_cursor.query.decode("utf-8"))
    return folder_id

