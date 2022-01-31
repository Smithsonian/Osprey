# Functions for MDfilecheck.py
# import datetime
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
import pandas


def check_requirements(program):
    """
    Check if required programs are installed
    """
    # From https://stackoverflow.com/a/34177358
    from shutil import which
    return which(program) is not None


def compress_log(filecheck_dir):
    """
    Compress log files
    """
    os.chdir('{}/logs'.format(filecheck_dir))
    for file in glob.glob('*.log'):
        subprocess.run(["zip", "{}.zip".format(file), file])
        os.remove(file)
    os.chdir(filecheck_dir)
    return True


def check_folder(folder_name, folder_path, project_id, db_cursor):
    """
    Check if a folder exists, add if it does not
    """
    if settings.folder_name == "server_folder":
        server_folder_path = folder_path.split("/")
        len_server_folder_path = len(server_folder_path)
        folder_name = "{}/{}".format(server_folder_path[len_server_folder_path - 2],
                                     server_folder_path[len_server_folder_path - 1])
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


def delete_folder_files(folder_id, db_cursor, logger):
    db_cursor.execute(queries.del_folder_files, {'folder_id': folder_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def folder_updated_at(folder_id, db_cursor, logger):
    """
    Update the last time the folder was checked
    """
    db_cursor.execute(queries.folder_updated_at, {'folder_id': folder_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def file_updated_at(file_id, db_cursor, logger):
    """
    Update the last time the file was checked
    """
    db_cursor.execute(queries.file_updated_at, {'file_id': file_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def jhove_validate(file_id, filename, db_cursor, logger):
    """
    Validate the file with JHOVE
    """
    # Where to write the results
    xml_file = "{}/mdpp_{}.xml".format(settings.tmp_folder, randint(100, 100000))
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
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def magick_validate(file_id, filename, db_cursor, logger, paranoid=False):
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
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def tif_compression(file_id, filename, db_cursor, logger):
    """
    Check if the image has compression
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
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def valid_name(file_id, filename, db_cursor, logger):
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
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def tifpages(file_id, filename, db_cursor, logger):
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
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def file_exif(file_id, filename, filetype, db_cursor, logger):
    """
    Extract the EXIF info from the RAW file
    """
    p = subprocess.Popen(['exiftool', '-t', '-a', '-U', '-u', '-D', '-G1', '-s', filename], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    if p.returncode == 0:
        exif_read = 0
    else:
        exif_read = 1
    exif_info = out
    for line in exif_info.splitlines():
        # Non utf, ignore for now
        try:
            tag = re.split(r'\t+', line.decode('UTF-8'))
            db_cursor.execute(queries.save_exif,
                              {'file_id': file_id, 'filetype': filetype, 'taggroup': tag[0], 'tagid': tag[1],
                               'tag': tag[2], 'value': tag[3]})
            logger.debug(db_cursor.query.decode("utf-8"))
        except Exception as e:
            logger.error("Tag not in utf-8 for file {}, {} {} {} ({})".format(file_id, tag[0], tag[1], tag[2], e))
            continue
    return True


# def itpc_validate(file_id, filename, db_cursor):
#     """
#     Check the IPTC Metadata
#     2Do
#     """
#     return False


def file_size_check(filename, filetype, file_id, db_cursor, logger):
    """
    Check if a file is within the size limits
    """
    import bitmath
    file_size = os.path.getsize(filename)
    if filetype == "tif":
        if file_size < settings.tif_size_min:
            file_size = 1
            file_size_info = "TIF file is smaller than expected ({})".format(
                bitmath.getsize(filename, system=bitmath.SI))
        elif file_size > settings.tif_size_max:
            file_size = 1
            file_size_info = "TIF file is larger than expected ({})".format(
                bitmath.getsize(filename, system=bitmath.SI))
        else:
            file_size = 0
            file_size_info = "{}".format(bitmath.getsize(filename, system=bitmath.SI))
        file_check = 'tif_size'
    elif filetype == "raw":
        if file_size < settings.raw_size_min:
            file_size = 1
            file_size_info = "RAW file is smaller than expected ({})".format(
                bitmath.getsize(filename, system=bitmath.SI))
        elif file_size > settings.raw_size_max:
            file_size = 1
            file_size_info = "RAW file is larger than expected ({})".format(
                bitmath.getsize(filename, system=bitmath.SI))
        else:
            file_size = 0
            file_size_info = "{}".format(bitmath.getsize(filename, system=bitmath.SI))
        file_check = 'raw_size'
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': file_check, 'check_results': file_size,
                                           'check_info': file_size_info})
    logger.debug(db_cursor.query.decode("utf-8"))
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


def file_pair_check(file_id, filename, tif_path, file_tif, raw_path, file_raw, db_cursor, logger):
    """
    Check if a file has a pair (tif + raw)
    """
    file_stem = Path(filename).stem
    # Check if file pair is present
    tif_file = "{}/{}.{}".format(tif_path, file_stem, file_tif)
    raw_file = "{}/{}.{}".format(raw_path, file_stem, file_raw)
    if os.path.isfile(tif_file) is False:
        # Tif file is missing
        file_pair = 1
        file_pair_info = "Missing tif"
    elif os.path.isfile(raw_file) is False:
        # Raw file is missing
        file_pair = 1
        file_pair_info = "Missing {} file".format(settings.raw_files)
    else:
        file_pair = 0
        file_pair_info = "tif and {} found".format(settings.raw_files)
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'raw_pair', 'check_results': file_pair,
                                           'check_info': file_pair_info})
    logger.debug(db_cursor.query.decode("utf-8"))
    return True


def check_jpg(file_id, filename, db_cursor, logger):
    """
    Run checks for jpg files
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
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'jpg', 'check_results': magick_identify,
                                           'check_info': magick_identify_info.decode("utf-8").replace("'", "''")})
    logger.debug(db_cursor.query.decode("utf-8"))
    if magick_return:
        # Store MD5
        file_md5 = filemd5(filename)
        db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'jpg', 'md5': file_md5})
        logger.debug(db_cursor.query.decode("utf-8"))
    return True


def checkmd5file(md5_file, folder_id, filetype, db_cursor, logger):
    """
    Check if md5 hashes match with the files
    -In progress
    """
    md5_error = ""
    if filetype == "tif":
        db_cursor.execute(queries.select_tif_md5, {'folder_id': folder_id, 'filetype': 'tif'})
    elif filetype == "raw":
        db_cursor.execute(queries.select_tif_md5, {'folder_id': folder_id, 'filetype': 'raw'})
    logger.debug(db_cursor.query.decode("utf-8"))
    vendor = pandas.DataFrame(db_cursor.fetchall(), columns=['md5_1', 'filename'])
    md5file = pandas.read_csv(md5_file, header=None, names=['md5_2', 'filename'], index_col=False, sep="  ")
    # Remove suffix
    if filetype == "tif":
        md5file['filename'] = md5file['filename'].str.replace(".tif", "")
        md5file['filename'] = md5file['filename'].str.replace(".TIF", "")
    elif filetype == "raw":
        md5file['filename'] = md5file['filename'].str.replace(".{}".format(settings.raw_files.lower()), "")
        md5file['filename'] = md5file['filename'].str.replace(".{}".format(settings.raw_files.upper()), "")
    md5check = pandas.merge(vendor, md5file, how="outer", on="filename")
    # MD5 hashes don't match
    # Get rows where MD5 don't match
    md5check_match = md5check[md5check.md5_1 != md5check.md5_2]
    # Ignore NAs
    md5check_match = md5check_match.dropna()
    # check if there are any mismatches
    nrows = len(md5check_match)
    if nrows > 0:
        md5_error = md5_error + "There were {} files where the MD5 hash did not match:".format(nrows)
        for i in range(0, nrows):
            md5_error = md5_error + "\n - File: {}, MD5 of file: {}, hash in file: {}".format(
                md5check_match['filename'][i], md5check_match['md5_2'], md5check_match['md5_1'])
    # Extra files in vendor mount
    vendor_extras = vendor[~vendor.filename.isin(md5file.filename)]['filename']
    # Extra files in md5file
    md5file_extras = md5file[~md5file.filename.isin(vendor.filename)]['filename']
    return True


def check_deleted(filetype, db_cursor, logger):
    """
    Deleted files are tagged in the database
    """
    # Get path
    if filetype == 'tif':
        files_path = settings.tif_files_path
    elif filetype == 'wav':
        files_path = settings.wav_files_path
    elif filetype == 'raw':
        files_path = settings.raw_files_path
    elif filetype == 'jpg':
        files_path = settings.jpg_files_path
    else:
        return False
    db_cursor.execute(queries.get_files, {'project_id': settings.project_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    files = db_cursor.fetchall()
    for file in files:
        if os.path.isdir("{}/{}/".format(file[2], files_path)):
            if os.path.isfile("{}/{}/{}.{}".format(file[2], files_path, file[1], filetype)):
                # file_exists = 0
                file_exists_info = "File {}/{}/{}.{} was found".format(file[2], files_path, file[1], filetype)
            else:
                # file_exists = 1
                file_exists_info = "File {}/{}/{}.{} was not found, deleting".format(file[2], files_path, file[1],
                                                                                     filetype)
                db_cursor.execute(queries.delete_file, {'file_id': file[0]})
                logger.debug(db_cursor.query.decode("utf-8"))
            logger.info(file_exists_info)
    return True


def check_stitched_jpg(file_id, filename, db_cursor, logger):
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
    logger.debug(db_cursor.query.decode("utf-8"))
    if magick_return:
        # Store MD5
        file_md5 = filemd5(filename)
        db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'jpg', 'md5': file_md5})
        logger.debug(db_cursor.query.decode("utf-8"))
    return True


def jpgpreview(file_id, folder_id, filename, logger):
    """
    Create preview image
    """
    if settings.jpg_previews == "":
        logger.error("JPG preview folder is not set in settings file")
        sys.exit(1)
    disk_check = shutil.disk_usage(settings.jpg_previews)
    if ((disk_check.free / disk_check.total) < 0.1):
        logger.error("JPG storage location is running out of space ({}%) - {}".format(
            round(disk_check.free / disk_check.total, 4) * 100, settings.jpg_previews))
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
            logger.info("JPG preview {} exists".format(preview_image))
            return True
    logger.info("creating preview_image:{}".format(preview_image))
    if settings.previews_size == "full":
        p = subprocess.Popen(['convert', '-quiet', "{}[0]".format(filename), preview_image], stdout=PIPE, stderr=PIPE)
    else:
        p = subprocess.Popen(['convert', '-quiet', "{}[0]".format(filename), '-resize',
                              '{imgsize}x{imgsize}'.format(imgsize=settings.previews_size), preview_image], stdout=PIPE,
                             stderr=PIPE)
    out = p.communicate()
    if os.path.isfile(preview_image):
        logger.info(out)
        return True
    else:
        logger.error("File:{}|msg:{}".format(filename, out))
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


def process_image(filename, folder_path, folder_id, logger):
    """
    Run checks for tif files
    """
    folder_id = int(folder_id)
    tmp_folder = "{}/{}".format(settings.tmp_folder, randint(100, 1000000))
    if os.path.isdir(tmp_folder):
        tmp_folder = "{}/{}".format(settings.tmp_folder, randint(100, 1000000))
    os.makedirs(tmp_folder)
    # logger.info("TIF file {}".format(filename))
    filename_stem = Path(filename).stem
    # Check if file exists, insert if not
    db_cursor.execute(queries.select_file_id, {'file_name': filename_stem, 'folder_id': folder_id})
    logger.debug(db_cursor.query.decode("utf-8"))
    file_id = db_cursor.fetchone()
    if file_id is None:
        # Get modified date for file
        if fileformat == "tif":
            img_files_path = settings.tif_files_path
        elif fileformat == "jpg":
            img_files_path = settings.jpg_files_path
        file_timestamp_float = os.path.getmtime("{}/{}/{}".format(folder_path, img_files_path, filename))
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        db_cursor.execute(queries.insert_file,
                          {'file_name': filename_stem, 'folder_id': folder_id, 'file_timestamp': file_timestamp})
        logger.debug(db_cursor.query.decode("utf-8"))
        file_id = db_cursor.fetchone()[0]
    else:
        file_id = file_id[0]
    print("file_id: {}".format(file_id))
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
    # Old path
    preview_file_path = "{}/{}".format(settings.jpg_previews, str(file_id)[0:2])
    preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
    if os.path.isfile(preview_image) is False:
        preview_file_path = "{}/folder{}".format(settings.jpg_previews, str(folder_id))
        preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
        if os.path.isfile(preview_image) is False:
            logger.info("jpg_preview {} does not exist for file_id:{}".format(preview_image, file_id))
            file_checks = file_checks + 1
    if fileformat == "tif":
        # Get filesize from TIF:
        file_size = os.path.getsize("{}/{}/{}.tif".format(folder_path, settings.tif_files_path, filename_stem))
        db_cursor.execute(queries.save_filesize, {'file_id': file_id, 'filetype': 'TIF', 'filesize': file_size})
        logger.debug(db_cursor.query.decode("utf-8"))
        # Get filesize from RAW:
        if os.path.isfile(
                "{}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem, settings.raw_files)):
            file_size = os.path.getsize(
                "{}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem, settings.raw_files))
            db_cursor.execute(queries.save_filesize, {'file_id': file_id, 'filetype': 'RAW', 'filesize': file_size})
            logger.debug(db_cursor.query.decode("utf-8"))
    # Get exif from TIF
    if fileformat == "tif":
        db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': 'TIF'})
    elif fileformat == "jpg":
        db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': 'JPG'})
    check_exif = db_cursor.fetchone()[0]
    logger.debug("check_exif_tif: {}".format(check_exif))
    if check_exif == 0:
        file_checks = file_checks + 1
    # Check if MD5 is stored
    if fileformat == "tif":
        db_cursor.execute(queries.select_file_md5, {'file_id': file_id, 'filetype': 'tif'})
    elif fileformat == "jpg":
        db_cursor.execute(queries.select_file_md5, {'file_id': file_id, 'filetype': 'jpg'})
    logger.debug(db_cursor.query.decode("utf-8"))
    result = db_cursor.fetchone()
    if result is None:
        logger.info("file_id:{};file_checks:{};result:None".format(file_id, 'md5'))
        file_checks = file_checks + 1
    if file_checks == 0:
        file_updated_at(file_id, db_cursor, logger)
        logger.info("File with ID {} is OK, skipping".format(file_id))
        shutil.rmtree(tmp_folder, ignore_errors=True)
        return True
    else:
        logger.info("file_checks: {} file_id: {}".format(file_checks, file_id))
        # Checks that do not need a local copy
        if 'raw_pair' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'raw_pair'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # FilePair check
                pair_check = file_pair_check(file_id, filename, "{}/{}".format(folder_path, settings.tif_files_path),
                                             'tif', "{}/{}".format(folder_path, settings.raw_files_path),
                                             settings.raw_files, db_cursor, logger)
                logger.info("pair_check:{}".format(pair_check))
                file_md5 = filemd5(
                    "{}/{}.{}".format("{}/{}".format(folder_path, settings.raw_files_path), filename_stem,
                                      settings.raw_files))
                db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'raw', 'md5': file_md5})
                logger.debug(db_cursor.query.decode("utf-8"))
                file_checks = file_checks - 1
        if file_checks == 0:
            return True
        if 'valid_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'valid_name'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # valid name in file
                valid_name(file_id, filename_stem, db_cursor, logger)
                file_checks = file_checks - 1
        if file_checks == 0:
            return True
        if 'prefix' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'prefix'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                if filename.startswith(settings.filename_prefix):
                    prefix_check = 0
                    prefix_info = ""
                    file_checks = file_checks - 1
                else:
                    prefix_check = 1
                    prefix_info = "Filename doesn't start with the required prefix {}".format(settings.filename_prefix)
                db_cursor.execute(queries.file_check,
                                  {'file_id': file_id, 'file_check': 'prefix', 'check_results': prefix_check,
                                   'check_info': prefix_info})
                logger.debug(db_cursor.query.decode("utf-8"))
        if file_checks == 0:
            return True
        if 'unique_file' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'unique_file'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # Check in project
                db_cursor.execute(queries.check_unique, {'file_name': filename_stem, 'folder_id': folder_id,
                                                         'project_id': settings.project_id, 'file_id': file_id})
                logger.debug(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchall()
                if len(result) == 0:
                    unique_file = 0
                    db_cursor.execute(queries.file_check,
                                      {'file_id': file_id, 'file_check': 'unique_file', 'check_results': unique_file,
                                       'check_info': ""})
                    logger.debug(db_cursor.query.decode("utf-8"))
                    file_checks = file_checks - 1
                else:
                    unique_file = 1
                    for dupe in result:
                        db_cursor.execute(queries.not_unique, {'folder_id': dupe[1]})
                        logger.debug(db_cursor.query.decode("utf-8"))
                        folder_dupe = db_cursor.fetchone()
                        db_cursor.execute(queries.file_check,
                                          {'file_id': dupe[0], 'file_check': 'unique_file', 'check_results': 1,
                                           'check_info': "File with same name in {}".format(folder_path)})
                        logger.debug(db_cursor.query.decode("utf-8"))
                        db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'unique_file',
                                                               'check_results': unique_file,
                                                               'check_info': "File with same name in {}".format(
                                                                   folder_dupe[0])})
                        logger.debug(db_cursor.query.decode("utf-8"))
        if 'unique_file_all' in settings.project_file_checks:
            # Check in other projects
            db_cursor.execute(queries.check_unique_all,
                              {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id,
                               'file_id': file_id})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()
            if result is None:
                unique_file = 0
                check_info = ""
            elif result[0] > 0:
                unique_file = 1
                db_cursor.execute(queries.not_unique_all,
                                  {'file_id': file_id, 'file_name': filename_stem, 'project_id': settings.project_id})
                logger.debug(db_cursor.query.decode("utf-8"))
                folder_check = db_cursor.fetchone()
                folder_dupe = folder_check[0]
                alt_project_id = folder_check[1]
                check_info = "File with same name in {} of project {}".format(folder_check[0], folder_check[1])
                file_checks = file_checks - 1
            else:
                unique_file = 0
                check_info = ""
            db_cursor.execute(queries.file_check,
                              {'file_id': file_id, 'file_check': 'unique_file_all', 'check_results': unique_file,
                               'check_info': check_info})
            logger.debug(db_cursor.query.decode("utf-8"))
        if file_checks == 0:
            return True
        if 'old_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                db_cursor.execute(queries.check_unique_old, {'file_name': filename_stem, 'folder_id': folder_id,
                                                             'project_id': settings.project_id})
                logger.debug(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchall()
                if len(result) > 0:
                    old_name = 1
                    folders = ",".join(result[0])
                else:
                    old_name = 0
                    folders = ""
                db_cursor.execute(queries.file_check,
                                  {'file_id': file_id, 'file_check': 'old_name', 'check_results': old_name,
                                   'check_info': folders})
                logger.debug(db_cursor.query.decode("utf-8"))
                file_checks = file_checks - 1
        if file_checks == 0:
            logger.info("file_checks: {};skipping file {}".format(file_checks, file_id))
            return True
        # Checks that DO need a local copy
        # Check if there is enough space first
        local_disk = shutil.disk_usage(settings.tmp_folder)
        if (local_disk.free / local_disk.total < 0.1):
            logger.error(
                "Disk is running out of space ({}%) - {}".format(round(local_disk.free / local_disk.total, 4) * 100,
                                                                 settings.tmp_folder))
            sys.exit(1)
        logger.info("file_checks: {}".format(file_checks))
        logger.info("Copying file {} to local tmp".format(filename))
        # Copy file to tmp folder
        local_tempfile = "{}/{}".format(tmp_folder, filename)
        # Check if file already exists
        if os.path.isfile(local_tempfile):
            os.remove(local_tempfile)
        if fileformat == "tif":
            img_files_path = settings.tif_files_path
        elif fileformat == "jpg":
            img_files_path = settings.jpg_files_path
        try:
            shutil.copyfile("{}/{}/{}".format(folder_path, img_files_path, filename), local_tempfile)
        except Exception as e:
            logger.error(
                "Could not copy file {}/{}/{} to local tmp ({})".format(folder_path, img_files_path, filename, e))
            db_cursor.execute(queries.file_exists, {'file_exists': 1, 'file_id': file_id})
            logger.debug(db_cursor.query.decode("utf-8"))
            sys.exit(1)
        # Generate jpg preview, if needed
        jpg_prev = jpgpreview(file_id, folder_id, local_tempfile, logger)
        # Compare MD5 between source and copy
        db_cursor.execute(queries.select_file_md5, {'file_id': file_id, 'filetype': fileformat})
        logger.debug(db_cursor.query.decode("utf-8"))
        result = db_cursor.fetchone()
        if result is None:
            logger.info("Getting MD5")
            sourcefile_md5 = filemd5("{}/{}/{}".format(folder_path, img_files_path, filename))
            # Store MD5
            file_md5 = filemd5(local_tempfile)
            if sourcefile_md5 != file_md5:
                logger.error(
                    "MD5 hash of local copy does not match the source: {} vs {}".format(sourcefile_md5, file_md5))
                return False
            db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': fileformat, 'md5': file_md5})
            logger.debug(db_cursor.query.decode("utf-8"))
            logger.info("{}_md5:{}".format(fileformat, file_md5))
        if 'jhove' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'jhove'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # JHOVE check
                jhove_validate(file_id, local_tempfile, db_cursor, logger)
        # if 'itpc' in settings.project_file_checks:
        #     db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'itpc'})
        #     logger.debug(db_cursor.query.decode("utf-8"))
        #     result = db_cursor.fetchone()[0]
        #     if result != 0:
        #         # ITPC Metadata
        #         itpc_validate(file_id, filename, db_cursor)
        if 'tif_size' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tif_size'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # File size check
                file_size_check(local_tempfile, "tif", file_id, db_cursor, logger)
        if 'magick' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'magick'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # Imagemagick check
                magick_validate(file_id, local_tempfile, db_cursor, logger)
        if 'jpg' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'jpg'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # JPG check
                check_jpg(file_id, "{}/{}/{}.jpg".format(folder_path, settings.jpg_files_path, filename_stem),
                          db_cursor, logger)
        if 'stitched_jpg' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'stitched_jpg'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # JPG check
                stitched_name = filename_stem.replace(settings.jpgstitch_original_1, settings.jpgstitch_new)
                stitched_name = stitched_name.replace(settings.jpgstitch_original_2, settings.jpgstitch_new)
                check_stitched_jpg(file_id, "{}/{}/{}.jpg".format(folder_path, settings.jpg_files_path, stitched_name),
                                   db_cursor, logger)
        if 'tifpages' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tifpages'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # check if tif has multiple pages
                tifpages(file_id, local_tempfile, db_cursor, logger)
        if 'tif_compression' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tif_compression'})
            logger.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                # check if tif is compressed
                tif_compression(file_id, local_tempfile, db_cursor, logger)
        # Get exif from TIF
        db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': fileformat.upper()})
        check_exif = db_cursor.fetchone()[0]
        logger.info("check_exif_tif: {}".format(check_exif))
        if check_exif == 0:
            logger.info(
                "Getting EXIF from {}/{}/{}".format(folder_path, img_files_path, filename))
            file_exif(file_id, local_tempfile, fileformat.upper(), db_cursor, logger)
        if settings.project_type == "tif":
            # Get exif from RAW
            db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': 'RAW'})
            check_exif = db_cursor.fetchone()[0]
            logger.info("check_exif_raw: {}".format(check_exif))
            if check_exif == 0:
                if os.path.isfile(
                        "{}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem, settings.raw_files)):
                    logger.info(
                        "Getting EXIF from {}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem,
                                                               settings.raw_files))
                    file_exif(file_id,
                              "{}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem,
                                                   settings.raw_files),
                              'RAW', db_cursor, logger)
        logger.info("jpg_prev:{}".format(jpg_prev))
        if os.path.isfile(local_tempfile):
            os.remove(local_tempfile)
        file_updated_at(file_id, db_cursor, logger)
        shutil.rmtree(tmp_folder, ignore_errors=True)
        return True
