#!/usr/bin/env python3
#
# Validate products from a vendor, usually images
# Version 0.4.5

############################################
# Import modules
############################################
import os, sys, shutil, subprocess, locale, logging, time, glob
import xmltodict, json, bitmath, pandas
#import exifread
from random import shuffle
#For Postgres
import psycopg2
#For MD5
import hashlib
from time import localtime, strftime
from pathlib import Path
from subprocess import Popen,PIPE
from datetime import datetime
#For parallel
from functools import partial
from itertools import repeat
import multiprocessing as mp


##Import settings from settings.py file
import settings


##Import queries from queries.py file
import queries


##System Settings
jhove_path = settings.jhove_path


##Save current directory
filecheck_dir = os.getcwd()


##Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')




############################################
# Logging
############################################
if not os.path.exists('logs'):
    os.makedirs('logs')
current_time = strftime("%Y%m%d%H%M%S", localtime())
logfile = 'logs/' + current_time + '.log'
# from http://stackoverflow.com/a/9321890
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M:%S',
                    filename=logfile,
                    filemode='a')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)
logger1 = logging.getLogger("vendor")




############################################
# Functions
############################################

def check_folder(folder_name, folder_path, project_id, db_cursor):
    """
    Check if a folder exists, add if it does not
    """
    if settings.folder_name == "server_folder":
        server_folder_path = folder_path.split("/")
        len_server_folder_path = len(server_folder_path)
        folder_name = "{}/{}".format(server_folder_path[len_server_folder_path-2], server_folder_path[len_server_folder_path-1])
    q = queries.select_folderid.format(folder_name, project_id)
    logger1.info(q)
    db_cursor.execute(q)
    folder_id = db_cursor.fetchone()
    if folder_id == None:
        #Folder does not exists, create
        q_insert = queries.new_folder.format(folder_name, folder_path, project_id)
        logger1.info(q)
        db_cursor.execute(q_insert)
        folder_id = db_cursor.fetchone()
    if settings.folder_date != "":
        #Update to set date of folder
        query_date = queries.folder_date.format(settings.folder_date, folder_id[0])
        logger1.info(query_date)
        db_cursor.execute(query_date)
    return folder_id[0]



def folder_updated_at(folder_id, db_cursor):
    """
    Update the last time the folder was checked
    """
    q_update = queries.folder_updated_at.format(folder_id)
    logger1.info(q_update)
    db_cursor.execute(q_update)
    return folder_id



def file_updated_at(file_id, db_cursor):
    """
    Update the last time the file was checked
    """
    q_update = queries.file_updated_at.format(file_id)
    logger1.info(q_update)
    db_cursor.execute(q_update)
    return file_id



def jhove_validate(file_id, filename, tmp_folder, db_cursor):
    """
    Validate the file with JHOVE
    """
    #Get the file name without the path
    base_filename = Path(filename).name
    #Where to write the results
    xml_file = "{}/mdpp_{}.xml".format(tmp_folder, base_filename)
    if os.path.isfile(xml_file):
        os.unlink(xml_file)
    #Run JHOVE
    subprocess.run([jhove_path, "-m", "TIFF-hul", "-h", "xml", "-o", xml_file, filename])
    #Open and read the results xml
    try:
        with open(xml_file) as fd:
            doc = xmltodict.parse(fd.read())
    except:
        error_msg = "Could not find result file from JHOVE ({})".format(xml_file)
        logger1.error(error_msg)
        q_jhove = queries.jhove.format(1, error_msg, file_id)
        logger1.info(q_jhove)
        db_cursor.execute(q_jhove)
        return False
    if os.path.isfile(xml_file):
        os.unlink(xml_file)
    #Get file status
    file_status = doc['jhove']['repInfo']['status']
    if file_status == "Well-Formed and valid":
        jhove_val = 0
    else:
        jhove_val = 1
        if len(doc['jhove']['repInfo']['messages']) == 1:
            #If the only error is with the WhiteBalance, ignore
            # Issue open at Github, seems will be fixed in future release
            # https://github.com/openpreserve/jhove/issues/364
            if doc['jhove']['repInfo']['messages']['message']['#text'][:31] == "WhiteBalance value out of range":
                jhove_val = 0
        file_status = doc['jhove']['repInfo']['messages']['message']['#text']
    q_jhove = queries.jhove.format(jhove_val, file_status, file_id)
    logger1.info(q_jhove)
    db_cursor.execute(q_jhove)
    return file_status




def jhove_validate_wav(file_id, filename, tmp_folder, db_cursor):
    """
    Validate the file with JHOVE
    """
    #Get the file name without the path
    base_filename = Path(filename).name
    #Where to write the results
    xml_file = "{}/mdpp_{}.xml".format(tmp_folder, base_filename)
    if os.path.isfile(xml_file):
        os.unlink(xml_file)
    #Run JHOVE
    subprocess.run([jhove_path, "-m", "wave-hul", "-h", "xml", "-o", xml_file, filename])
    #Open and read the results xml
    try:
        with open(xml_file) as fd:
            doc = xmltodict.parse(fd.read())
    except:
        error_msg = "Could not find result file from JHOVE ({})".format(xml_file)
        logger1.error(error_msg)
        q_jhove = queries.jhove.format(1, error_msg, file_id)
        logger1.info(q_jhove)
        db_cursor.execute(q_jhove)
        return False
    if os.path.isfile(xml_file):
        os.unlink(xml_file)
    #Get file status
    file_status = doc['jhove']['repInfo']['status']
    if file_status == "Well-Formed and valid":
        jhove_val = 0
    else:
        jhove_val = 1
        if len(doc['jhove']['repInfo']['messages']) == 1:
            #If the only error is with the WhiteBalance, ignore
            # Issue open at Github, seems will be fixed in future release
            # https://github.com/openpreserve/jhove/issues/364
            if doc['jhove']['repInfo']['messages']['message']['#text'][:31] == "WhiteBalance value out of range":
                jhove_val = 0
        file_status = doc['jhove']['repInfo']['messages']['message']['#text']
    q_jhove = queries.jhove.format(jhove_val, file_status, file_id)
    logger1.info(q_jhove)
    db_cursor.execute(q_jhove)
    return file_status



def magick_validate(file_id, filename, db_cursor, paranoid = False):
    """
    Validate the file with Imagemagick
    """
    if paranoid == True:
        p = subprocess.Popen(['identify', '-verbose', '-regard-warnings', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        p = subprocess.Popen(['identify', '-verbose', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out,err) = p.communicate()
    if p.returncode == 0:
        magick_identify = 0
        return_code = True
    else:
        magick_identify = 1
        return_code = False
    magick_identify_info = out + err
    q_pair = queries.magick.format(magick_identify, magick_identify_info.decode("utf-8").replace("'", "''"), file_id)
    logger1.info(q_pair)
    db_cursor.execute(q_pair)
    return return_code



def valid_name(file_id, filename, db_cursor, paranoid = False):
    """
    Check if filename in database of accepted names
    """
    db_cursor.execute(settings.filename_pattern_query.format(Path(filename).stem))
    valid_names = db_cursor.fetchone()[0]
    if valid_names == 0:
        valid_filename_check = 1
        logger1.error("valid_name:{} not in database".format(Path(filename).stem))
        return_code = False
    else:
        valid_filename_check = 0
        logger1.info("valid_name:{} in database".format(Path(filename).stem))
        return_code = True
    valid_name_q = queries.filename_query.format(valid_filename_check, file_id)
    db_cursor.execute(valid_name_q)
    return return_code



def tifpages(file_id, filename, db_cursor, paranoid = False):
    """
    Check if TIF has multiple pages
    """
    p = subprocess.Popen(['identify', '-format', '%n', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out,err) = p.communicate()
    try:
        no_pages = int(out)
        if int(out) == 1:
            pages_vals = 0
            return_code = True
        else:
            pages_vals = 1
            return_code = False
    except:
        no_pages = "Unknown"
        pages_vals = 1
        return_code = False
    q_multipage = queries.update_tif_pages.format(pages_vals, no_pages, file_id)
    logger1.info(q_multipage)
    db_cursor.execute(q_multipage)
    return return_code



def jpgpreview(file_id, filename, db_cursor, paranoid = False):
    """
    Create preview image
    """
    preview_file_path = "{}/{}".format(settings.jpg_previews, str(file_id)[0:2])
    preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
    #Create subfolder if it doesn't exists
    if not os.path.exists(preview_file_path):
        os.makedirs(preview_file_path)
    #Delete old image, if exists
    if os.path.isfile(preview_image):
        os.unlink(preview_image)
    logger1.info("preview_image:{}".format(preview_image))
    try:
        p = subprocess.run(['convert', "{}[0]".format(filename), '-resize', '1000x1000', preview_image], stdout=PIPE,stderr=PIPE)
        return True
    except:
        return False



def itpc_validate(file_id, filename, db_cursor):
    """
    Check the IPTC Metadata
    Need to rewrite using exifread
    """
    # metadata = pyexiv2.ImageMetadata(filename)
    # iptc_metadata = 0
    # iptc_metadata_info = "IPTC Metadata exists"
    # return_code = True
    # try:
    #     iptc_metadata_info = metadata.read()
    # except:
    #     iptc_metadata = 1
    #     iptc_metadata_info = "Could not read metadata"
    #     return_code = False
    # #for meta in metadata.exif_keys:
    # #    print(metadata[meta].value)
    # #logger1.info(meta_check)
    # q_meta = "UPDATE files SET iptc_metadata = {}, iptc_metadata_info = '{}' WHERE file_id = {}".format(iptc_metadata, iptc_metadata_info, file_id)
    # logger1.info(q_meta)
    # db_cursor.execute(q_meta)
    return False



def file_pair_check(file_id, filename, tif_path, file_tif, raw_path, file_raw, db_cursor):
    """
    Check if a file has a pair (tif + raw)
    """
    base_filename = Path(filename).name
    path_filename = Path(filename).parent
    file_stem = Path(filename).stem
    #Check if file pair is present
    tif_file = "{}/{}.{}".format(tif_path, file_stem, file_tif)
    raw_file = "{}/{}.{}".format(raw_path, file_stem, file_raw)
    if os.path.isfile(tif_file) != True:
        #Tif file is missing
        file_pair = 1
        file_pair_info = "Missing tif"
    elif os.path.isfile(raw_file) != True:
        #Raw file is missing
        file_pair = 1
        file_pair_info = "Missing {} file".format(settings.raw_files)
    else:
        file_pair = 0
        file_pair_info = "tif and {} found".format(settings.raw_files)
    q_pair = queries.filepair.format(file_pair, file_pair_info, file_id)
    logger1.info(q_pair)
    db_cursor.execute(q_pair)
    return (os.path.isfile(tif_file), os.path.isfile(raw_file))



def soxi_check(file_id = "0", filename = "", file_check = "filetype", expected_val = "", db_cursor = ""):
    """
    Get the tech info of a wav file
    """
    if file_check == "filetype":
        fcheck = "t"
    elif file_check == "samprate":
        fcheck = "r"
    elif file_check == "channels":
        fcheck = "c"
    elif file_check == "duration":
        fcheck = "D"
    elif file_check == "bits":
        fcheck = "b"
    p = subprocess.Popen(['soxi', '-{}'.format(fcheck), filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out,err) = p.communicate()
    result = out.decode("utf-8").replace('\n','')
    err = err.decode("utf-8").replace('\n','')
    if file_check == "filetype":
        if result == expected_val:
            result_code = 0
        else:
            result_code = 1
    elif file_check == "samprate":
        if result == expected_val:
            result_code = 0
        else:
            result_code = 1
    elif file_check == "channels":
        if result == expected_val:
            result_code = 0
        else:
            result_code = 1
    elif file_check == "duration":
        if result == expected_val:
            result_code = 0
        else:
            result_code = 1
    elif file_check == "bits":
        if result == expected_val:
            result_code = 0
        else:
            result_code = 1
    # if p.returncode == 0:
    #     res_val = 0
    #     return_code = True
    # else:
    #     res_val = 1
    #     return_code = False
    q_soxi = queries.soxi.format(file_id = file_id, field = file_check, res_value = result_code, result = result)
    logger1.info(q_soxi)
    db_cursor.execute(q_soxi)
    return result_code



def file_size_check(filename, filetype, file_id, db_cursor):
    """
    Check if a file is within the size limits
    """
    file_size = os.path.getsize(filename)
    logger1.info(str(file_size))
    if filetype == "tif":
        if file_size < settings.tif_size_min:
            file_size = 1
            file_size_info = "TIF file is smaller than expected ({})".format(bitmath.getsize(filename, system=bitmath.SI))
        elif file_size > settings.tif_size_max:
            file_size = 1
            file_size_info = "TIF file is larger than expected ({})".format(bitmath.getsize(filename, system=bitmath.SI))
        else:
            file_size = 0
            file_size_info = "{}".format(bitmath.getsize(filename, system=bitmath.SI))
        q_size = queries.tif_size.format(file_size, file_size_info, file_id)
    elif filetype == "raw":
        if file_size < settings.raw_size_min:
            file_size = 1
            file_size_info = "RAW file is smaller than expected ({})".format(bitmath.getsize(filename, system=bitmath.SI))
        elif file_size > settings.raw_size_max:
            file_size = 1
            file_size_info = "RAW file is larger than expected ({})".format(bitmath.getsize(filename, system=bitmath.SI))
        else:
            file_size = 0
            file_size_info = "{}".format(bitmath.getsize(filename, system=bitmath.SI))
        q_size = queries.raw_size.format(file_size, file_size_info, file_id)
    logger1.info(q_size)
    db_cursor.execute(q_size)
    return True



def delete_folder_files(folder_id, db_cursor):
    q_insert = queries.del_folder_files.format(folder_id)
    logger1.info(q_insert)
    db_cursor.execute(q_insert)
    return True



def filemd5(file_id, filepath, filetype, db_cursor):
    """
    Get MD5 hash of a file
    """
    md5_hash = hashlib.md5()
    with open(filepath, "rb") as f:
        # Read and update hash in chunks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
    file_md5 = md5_hash.hexdigest()
    which_file = "{}_md5".format(filetype)
    q_insert = queries.update_md5.format(which_file, file_md5, file_id)
    logger1.info(q_insert)
    db_cursor.execute(q_insert)
    return True



def checkmd5file(md5_file, folder_id, filetype, db_cursor):
    """
    Check if md5 hashes match with the files
    -In progress
    """
    md5_error = ""
    if filetype == "tif":
        q_select = queries.select_tif_md5.format(folder_id)
    elif filetype == "raw":
        q_select = queries.select_raw_md5.format(folder_id)
    logger1.info(q_select)
    db_cursor.execute(q_select)
    vendor = pandas.DataFrame(db_cursor.fetchall(), columns = ['md5_1', 'filename'])
    md5file = pandas.read_csv(md5_file, header = None, names = ['md5_2', 'filename'], index_col = False, sep = "  ")
    #Remove suffix
    if filetype == "tif":
        md5file['filename'] = md5file['filename'].str.replace(".tif", "")
        md5file['filename'] = md5file['filename'].str.replace(".TIF", "")
    elif filetype == "raw":
        md5file['filename'] = md5file['filename'].str.replace(".{}".format(settings.raw_files.lower()), "")
        md5file['filename'] = md5file['filename'].str.replace(".{}".format(settings.raw_files.upper()), "")
    md5check = pandas.merge(vendor, md5file, how = "outer", on = "filename")
    ##MD5 hashes don't match
    #Get rows where MD5 don't match
    md5check_match = md5check[md5check.md5_1 != md5check.md5_2]
    #Ignore NAs
    md5check_match = md5check_match.dropna()
    #check if there are any mismatches
    nrows = len(md5check_match)
    if nrows > 0:
        md5_error = md5_error + "There were {} files where the MD5 hash did not match:".format(nrows)
        for i in range(0, nrows):
            md5_error = md5_error + "\n - File: {}, MD5 of file: {}, hash in file: {}".format(md5check_match['filename'][i], md5check_match['md5_2'], md5check_match['md5_1'])
    #
    ##Extra files in vendor mount
    vendor_extras = vendor[~vendor.filename.isin(md5file.filename)]['filename']
    ##Extra files in md5file
    md5file_extras = md5file[~md5file.filename.isin(vendor.filename)]['filename']
    return True



def check_jpg(file_id, filename, db_cursor):
    """
    Run checks for jpg files
    """
    p = subprocess.Popen(['identify', '-verbose', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out,err) = p.communicate()
    if p.returncode == 0:
        magick_identify = 0
        magick_identify_info = out
        magick_return = True
    else:
        magick_identify = 1
        magick_identify_info = err
        magick_return = False
    q_jpg = queries.set_jpg.format(magick_identify, magick_identify_info.decode("utf-8").replace("'", "''"), file_id)
    logger1.info(q_jpg)
    db_cursor.execute(q_jpg)
    if magick_return:
        #Save jpg preview
        preview_file_path = "{}/{}".format(settings.jpg_previews, str(file_id)[0:2])
        preview_image = "{}/{}_jpg.jpg".format(preview_file_path, file_id)
        #Create subfolder if it doesn't exists
        if not os.path.exists(preview_file_path):
            os.makedirs(preview_file_path)
        #Delete old image, if exists
        if os.path.isfile(preview_image):
            os.unlink(preview_image)
        p = subprocess.run(['convert', filename, '-resize', '1000x1000', preview_image])
        #Store MD5
        file_md5 = filemd5(file_id, filename, "jpg", db_cursor)
        logger1.info("jpg_md5:{}".format(file_md5))
    return magick_return



def process_tif(filename, folder_path, folder_id, folder_full_path, tmp_folder):
    """
    Run checks for tif files
    """
    folder_id = int(folder_id)
    #Connect to the database
    try:
        logger1.info("Connecting to database")
        conn2 = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, password = settings.db_password, connect_timeout = 60)
    except:
        logger1.error("Could not connect to server.")
        sys.exit(1)
    conn2.autocommit = True
    db_cursor = conn2.cursor()
    #Check if file exists, insert if not
    logger1.info("TIF file {}".format(filename))
    q_checkfile = queries.select_file_id.format(Path(filename).stem, folder_id)
    logger1.info(q_checkfile)
    db_cursor.execute(q_checkfile)
    file_id = db_cursor.fetchone()
    if file_id == None:
        q_checkunique = queries.check_unique.format(Path(filename).stem, folder_id, settings.project_id)
        logger1.info(q_checkunique)
        db_cursor.execute(q_checkunique)
        result = db_cursor.fetchone()
        if result[0] > 0:
            unique_file = 1
        else:
            unique_file = 0
        if unique_file == 0:        
            #Check for unique filename in table with old names      
            filter_substring = " AND file_folder NOT IN (SELECT split_part(project_folder, '/', 2) FROM folders WHERE folder_id = {})".format(folder_id)
            q_checkunique = queries.check_unique_old.format(Path(filename).stem, settings.project_id, filter_substring)
            logger1.info(q_checkunique)     
            db_cursor.execute(q_checkunique)        
            result = db_cursor.fetchone()       
            if result[0] > 0:       
                unique_file = 1     
            else:       
                unique_file = 0
        #Get modified date for file
        file_timestamp_float = os.path.getmtime("{}/{}/{}".format(folder_path, settings.tif_files_path, filename))
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        q_insert = queries.insert_file.format(folder_id, Path(filename).stem, unique_file, file_timestamp)
        logger1.info(q_insert)
        db_cursor.execute(q_insert)
        file_id = db_cursor.fetchone()[0]
        if settings.use_item_id == True:
            q_insert = queries.update_item_no.format(settings.item_id, file_id)
            logger1.info(q_insert)
            db_cursor.execute(q_insert)
        else:
            q_insert = queries.update_item_no.format("file_name", file_id)
            logger1.info(q_insert)
            db_cursor.execute(q_insert)
    else:
        file_id = file_id[0]
    print("file_id: {}".format(file_id))
    #Check if file is OK
    file_checks = 0
    for filecheck in settings.project_checks:
        q_checkfile = queries.select_check_file.format(filecheck, file_id)
        logger1.info(q_checkfile)
        db_cursor.execute(q_checkfile)
        result = db_cursor.fetchone()
        file_checks = file_checks + result[0]
    if file_checks == 0:
        file_updated_at(file_id, db_cursor)
        logger1.info("File with ID {} is OK, skipping".format(file_id))
        #Disconnect from db
        conn2.close()
        return True
    else:
        #Copy file to tmp folder
        local_tempfile = "{}/{}".format(tmp_folder, filename)
        try:
            shutil.copyfile("{}/{}".format(folder_full_path, filename), local_tempfile)
        except:
            query = settings.delete_file.format(folder_id)
            logger1.error("Could not copy file {}/{} to local tmp".format(folder_full_path, filename))
            logger1.info(query)
            db_cursor.execute(query)
            return False
        if 'file_pair' in settings.project_checks:
            #FilePair check
            pair_check = file_pair_check(file_id, filename, "{}/{}".format(folder_path, settings.tif_files_path), 'tif', "{}/{}".format(folder_path, settings.raw_files_path), settings.raw_files, db_cursor)
            logger1.info("pair_check:{}".format(pair_check))
        if 'jhove' in settings.project_checks:
            #JHOVE check
            jhove_check = jhove_validate(file_id, local_tempfile, tmp_folder, db_cursor)
            logger1.info("jhove_check:{}".format(jhove_check))
        if 'itpc' in settings.project_checks:
            #ITPC Metadata
            itpc_check = itpc_validate(file_id, filename, db_cursor)
            logger1.info("itpc_check:{}".format(itpc_check))
        if 'tif_size' in settings.project_checks:
            #File size check
            check_tif_size = file_size_check(local_tempfile, "tif", file_id, db_cursor)
            logger1.info("check_tif_size:{}".format(check_tif_size))
        if 'magick' in settings.project_checks:
            #Imagemagick check
            magickval = magick_validate(file_id, local_tempfile, db_cursor)
            logger1.info("magick_validate:{}".format(magick_validate))
        if 'jpg' in settings.project_checks:
            #JPG check
            jpg_check = check_jpg(file_id, "{}/{}/{}.jpg".format(folder_path, settings.jpg_files_path, Path(filename).stem), db_cursor)
            logger1.info("jpg_check:{}".format(jpg_check))
        if 'valid_name' in settings.project_checks:
            #valid name in file
            valname = valid_name(file_id, local_tempfile, db_cursor)
            logger1.info("valid_name:{}".format(valname))
        if 'tifpages' in settings.project_checks:
            #check if tif has multiple pages
            tif_pages = tifpages(file_id, local_tempfile, db_cursor)
            logger1.info("tif_pages:{}".format(tif_pages))
        if 'jpgpreview' in settings.special_checks: 
            #Create preview image
            jpg_prev = jpgpreview(file_id, local_tempfile, db_cursor)
            logger1.info("jpg_prev:{}".format(jpg_prev))
        if 'tif_md5' in settings.special_checks: 
            #Store MD5
            file_md5 = filemd5(file_id, "{}/{}/{}".format(folder_path, settings.tif_files_path, filename), "tif", db_cursor)
            logger1.info("tif_md5:{}".format(file_md5))
        if 'old_name' in settings.special_checks:
            filter_subquery = settings.oldname_subquery.format(folder_id)
            q_checkunique_old = queries.check_unique_old.format(Path(filename).stem, settings.project_id, filter_subquery)
            logger1.info(q_checkunique_old)
            db_cursor.execute(q_checkunique_old)
            result = db_cursor.fetchone()
            if result[0] > 0:
                db_cursor.execute(queries.not_unique.format(file_id))
        #Disconnect from db
        file_updated_at(file_id, db_cursor)
        conn2.close()
        os.remove(local_tempfile)
        return True



def process_raw(filename, folder_path, folder_id, raw, folder_full_path, tmp_folder):
    """
    Run checks for raw files
    """
    folder_id = int(folder_id)
    #Connect to the database
    try:
        logger1.info("Connecting to database")
        conn2 = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, password = settings.db_password, connect_timeout = 60)
    except:
        logger1.error("Could not connect to server.")
        sys.exit(1)
    conn2.autocommit = True
    db_cursor = conn2.cursor()
    #Check if file exists, insert if not
    logger1.info("RAW file {}".format(filename))
    q_checkfile = queries.select_file_id.format(Path(filename).stem, folder_id)
    logger1.info(q_checkfile)
    db_cursor.execute(q_checkfile)
    file_id = db_cursor.fetchone()
    if file_id == None:
        q_checkunique = queries.check_unique.format(Path(filename).stem, folder_id, settings.project_id)
        logger1.info(q_checkunique)
        db_cursor.execute(q_checkunique)
        result = db_cursor.fetchone()
        if result[0] > 0:
            unique_file = 1
        else:
            unique_file = 0
        #Get modified date for file
        file_timestamp_float = os.path.getmtime("{}/{}/{}".format(folder_path, settings.raw_files_path, filename))
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        print(file_timestamp)
        q_insert = queries.insert_file.format(folder_id, Path(filename).stem, unique_file, file_timestamp)
        logger1.info(q_insert)
        db_cursor.execute(q_insert)
        file_id = db_cursor.fetchone()[0]
        if settings.use_item_id == True:
            q_insert = queries.update_item_no.format(settings.item_id, file_id)
            logger1.info(q_insert)
            db_cursor.execute(q_insert)
        else:
            q_insert = queries.update_item_no.format("file_name", file_id)
            logger1.info(q_insert)
            db_cursor.execute(q_insert)
    else:
        file_id = file_id[0]
    print("file_id: {}".format(file_id))
    #Check if file is OK
    file_checks = 0
    for filecheck in settings.project_checks:
        q_checkfile = queries.select_check_file.format(filecheck, file_id)
        logger1.info(q_checkfile)
        db_cursor.execute(q_checkfile)
        result = db_cursor.fetchone()
        file_checks = file_checks + result[0]
    if file_checks == 0:
        logger1.info("File with ID {} is OK, skipping".format(file_id))
        #Disconnect from db
        conn2.close()
        return True
    else:
        #Copy file to tmp folder
        local_tempfile = "{}/{}".format(tmp_folder, filename)
        try:
            shutil.copyfile("{}/{}".format(folder_full_path, filename), local_tempfile)
        except:
            query = settings.delete_file.format(folder_id)
            logger1.error("Could not copy file {}/{} to local tmp".format(folder_full_path, filename))
            logger1.info(query)
            db_cursor.execute(query)
            return False
        if 'file_pair' in settings.project_checks:
            #FilePair check
            pair_check = file_pair_check(file_id, filename, folder_path + "/" + settings.tif_files_path, 'tif', folder_path + "/" + settings.raw_files_path, settings.raw_files, db_cursor)
            logger1.info("pair_check:{}".format(pair_check))
        if 'raw_size' in settings.project_checks:
            #File size check
            check_raw_size = file_size_check("{}/{}/{}".format(folder_path, settings.raw_files_path, filename), "raw", file_id, db_cursor)
            logger1.info("check_raw_size:{}".format(check_raw_size))
        if 'raw_md5' in settings.special_checks:
            #Store MD5
            file_md5 = filemd5(file_id, "{}/{}/{}".format(folder_path, settings.raw_files_path, filename), "raw", db_cursor)
            logger1.info("raw_md5:{}".format(file_md5))
        #Disconnect from db
        conn2.close()
        os.remove(local_tempfile)
        return True



def process_wav(filename, folder_path, folder_id, folder_full_path, tmp_folder):
    """
    Run checks for wav files
    """
    folder_id = int(folder_id)
    #Connect to the database
    try:
        logger1.info("Connecting to database")
        conn2 = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, password = settings.db_password, connect_timeout = 60)
    except:
        logger1.error("Could not connect to server.")
        sys.exit(1)
    conn2.autocommit = True
    db_cursor = conn2.cursor()
    #Check if file exists, insert if not
    logger1.info("WAV file {}".format(filename))
    q_checkfile = queries.select_file_id.format(Path(filename).stem, folder_id)
    logger1.info(q_checkfile)
    db_cursor.execute(q_checkfile)
    file_id = db_cursor.fetchone()
    if file_id == None:
        q_checkunique = queries.check_unique.format(Path(filename).stem, folder_id, settings.project_id)
        logger1.info(q_checkunique)
        db_cursor.execute(q_checkunique)
        result = db_cursor.fetchone()
        if result[0] > 0:
            unique_file = 1
        else:
            unique_file = 0
        if unique_file == 0:        
            #Check for unique filename in table with old names      
            filter_substring = " AND file_folder NOT IN (SELECT split_part(project_folder, '/', 2) FROM folders WHERE folder_id = {})".format(folder_id)
            q_checkunique = queries.check_unique_old.format(Path(filename).stem, settings.project_id, filter_substring)
            logger1.info(q_checkunique)     
            db_cursor.execute(q_checkunique)        
            result = db_cursor.fetchone()       
            if result[0] > 0:       
                unique_file = 1     
            else:       
                unique_file = 0
        #Get modified date for file
        file_timestamp_float = os.path.getmtime("{}/{}".format(folder_path, filename))
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        q_insert = queries.insert_file.format(folder_id, Path(filename).stem, unique_file, file_timestamp)
        logger1.info(q_insert)
        db_cursor.execute(q_insert)
        file_id = db_cursor.fetchone()[0]
        if settings.use_item_id == True:
            q_insert = queries.update_item_no.format(settings.item_id, file_id)
            logger1.info(q_insert)
            db_cursor.execute(q_insert)
        else:
            q_insert = queries.update_item_no.format("file_name", file_id)
            logger1.info(q_insert)
            db_cursor.execute(q_insert)
    else:
        file_id = file_id[0]
    print("file_id: {}".format(file_id))
    #Check if file is OK
    file_checks = 0
    for filecheck in settings.project_checks:
        q_checkfile = queries.select_check_file.format(filecheck, file_id)
        logger1.info(q_checkfile)
        db_cursor.execute(q_checkfile)
        result = db_cursor.fetchone()
        if result[0] != None:
            file_checks = file_checks + result[0]
    if file_checks == 0:
        file_updated_at(file_id, db_cursor)
        logger1.info("File with ID {} is OK, skipping".format(file_id))
        #Disconnect from db
        conn2.close()
        return True
    else:
        #Copy file to tmp folder
        local_tempfile = "{}/{}".format(tmp_folder, filename)
        try:
            shutil.copyfile("{}/{}".format(folder_full_path, filename), local_tempfile)
        except:
            query = settings.delete_file.format(folder_id)
            logger1.error("Could not copy file {}/{} to local tmp".format(folder_full_path, filename))
            logger1.info(query)
            db_cursor.execute(query)
            return False
        if 'filetype' in settings.project_checks:
            #FilePair check
            tech_info = soxi_check(file_id, filename, "filetype", settings.wav_filetype, db_cursor)
            logger1.info("tech_info:{}".format(tech_info))
        if 'samprate' in settings.project_checks:
            #FilePair check
            tech_info = soxi_check(file_id, filename, "samprate", settings.wav_samprate, db_cursor)
            logger1.info("tech_info:{}".format(tech_info))
        if 'channels' in settings.project_checks:
            #FilePair check
            tech_info = soxi_check(file_id, filename, "channels", settings.wav_channels, db_cursor)
            logger1.info("tech_info:{}".format(tech_info))
        if 'bits' in settings.project_checks:
            #FilePair check
            tech_info = soxi_check(file_id, filename, "bits", settings.wav_bits, db_cursor)
            logger1.info("tech_info:{}".format(tech_info))
        if 'jhove' in settings.project_checks:
            #JHOVE check
            jhove_check = jhove_validate_wav(file_id, local_tempfile, tmp_folder, db_cursor)
            logger1.info("jhove_check:{}".format(jhove_check))
        #Store MD5
        file_md5 = filemd5(file_id, "{}/{}".format(folder_path, filename), "wav", db_cursor)
        logger1.info("wav_md5:{}".format(file_md5))
        #Disconnect from db
        file_updated_at(file_id, db_cursor)
        conn2.close()
        os.remove(local_tempfile)
        return True



def check_deleted():
    """
    Deleted files are tagged in the database
    """
    #Connect to the database
    try:
        logger1.info("Connecting to database")
        con = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, password = settings.db_password, connect_timeout = 60)
    except:
        logger1.error("Could not connect to server.")
        sys.exit(1)
    con.autocommit = True
    db_cursor = con.cursor()
    get_files = queries.get_files.format(settings.project_id)
    logger1.info(get_files)
    db_cursor.execute(get_files)
    files = db_cursor.fetchall()
    for file in files:
        if os.path.isfile("{}/{}/{}.tif".format(file[2], settings.tif_files_path, file[1])) == True:
            logger1.info("File {}/{}/{}.tif was found".format(file[2], settings.tif_files_path, file[1]))
            q_foundfile = queries.file_exists.format(file[0])
            logger1.info(q_foundfile)
            db_cursor.execute(q_foundfile)
        else:
            logger1.error("File {}/{}/{}.tif was not found".format(file[2], settings.tif_files_path, file[1]))
            q_delfile = queries.delete_file.format(file[0])
            logger1.info(q_delfile)
            db_cursor.execute(q_delfile)
    con.close()
    return True



def main():
    #Check that the paths are mounted
    for p_path in settings.project_paths:
        if os.path.ismount(p_path) == False:
            logger1.error("Path not found: {}".format(p_path))
            time.sleep(settings.sleep)
            continue
    #Connect to the database
    try:
        logger1.info("Connecting to database")
        conn = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, password = settings.db_password, connect_timeout = 60)
    except:
        logger1.error("Could not connect to server.")
        sys.exit(1)
    conn.autocommit = True
    db_cursor = conn.cursor()
    #Update project
    q_project = queries.update_projectchecks.format(','.join(settings.project_checks), settings.project_id)
    logger1.info(q_project)
    db_cursor.execute(q_project)
    logger1.info(','.join(settings.project_paths))
    for project_path in settings.project_paths:
        logger1.info(project_path)
        #Generate list of folders
        folders = []
        #List of folders
        for entry in os.scandir(project_path):
            if entry.is_dir():
                folders.append(entry.path)
        shuffle(folders)
        #Check each folder
        for folder in folders:
            folder_path = folder
            folder_name = os.path.basename(folder)
            #tmp folder
            tmp_folder = "/tmp/tmp_{}".format(folder_name)
            if os.path.isdir(tmp_folder):
                shutil.rmtree(tmp_folder, ignore_errors = True)
            os.mkdir(tmp_folder)
            try:
                folder_id = check_folder(folder_name, folder_path, settings.project_id, db_cursor)
            except:
                logger1.error("Folder {} had an error".format(folder_name))
                continue
            q_folderreset = queries.update_folder_status0.format(folder_id)
            logger1.info(q_folderreset)
            db_cursor.execute(q_folderreset)
            if 'wavs' in settings.special_checks:
                q = queries.update_folder_0.format(folder_id)
                logger1.info(q)
                db_cursor.execute(q)
                ##############################
                #Check the files in parallel
                ##############################
                logger1.info(folder_path)
                folder_full_path = folder_path
                os.chdir(folder_full_path)
                files = glob.glob("*.wav")
                logger1.info(files)
                #Remove temp files
                if settings.ignore_string != None:
                    files = [ x for x in files if settings.ignore_string not in x ]
                logger1.info(files)
                #shuffle(files)
                #Parallel
                #Get time
                now = datetime.now()
                for file in files:
                    logger1.info("Running checks on file {}".format(file))
                    process_wav(file, folder_path, folder_id, folder_full_path, tmp_folder)
                # #Get hour and run the alternative number of workers during the night
                # if now.hour > 17 and now.hour < 7:
                #     pool = mp.Pool(settings.no_workers_night)
                # else:
                #     pool = mp.Pool(settings.no_workers)
                # res = pool.starmap(process_wav, zip(files, repeat(folder_path), repeat(folder_id), repeat(folder_full_path), repeat(tmp_folder)))
                # pool.close()
                #MD5
                for file in glob.glob("*.md5"):
                    q_md5 = queries.update_folders_md5.format("wav", folder_id)
                    logger1.info(q_md5)
                    db_cursor.execute(q_md5)
            else:
                if (os.path.isdir(folder_path + "/" + settings.raw_files_path) == False and os.path.isdir(folder_path + "/" + settings.tif_files_path) == False):
                    logger1.info("Missing TIF and RAW folders")
                    q = queries.update_folder_status9.format("both", folder_id)
                    logger1.info(q)
                    db_cursor.execute(q)
                    delete_folder_files(folder_id, db_cursor)
                    continue
                elif os.path.isdir(folder_path + "/" + settings.tif_files_path) == False:
                    logger1.info("Missing TIF folder")
                    q = queries.update_folder_status9.format(settings.tif_files_path, folder_id)
                    logger1.info(q)
                    db_cursor.execute(q)
                    delete_folder_files(folder_id, db_cursor)
                    continue
                elif os.path.isdir(folder_path + "/" + settings.raw_files_path) == False:
                    logger1.info("Missing RAW folder")
                    q = queries.update_folder_status9.format(settings.raw_files_path, folder_id)
                    logger1.info(q)
                    db_cursor.execute(q)
                    delete_folder_files(folder_id, db_cursor)
                    continue
                else:
                    logger1.info("Both folders present")
                    q = queries.update_folder_0.format(folder_id)
                    logger1.info(q)
                    db_cursor.execute(q)
                    #Both folders present
                    ##############################
                    #Check the tifs in parallel
                    ##############################
                    folder_full_path = "{}/{}".format(folder_path, settings.tif_files_path)
                    os.chdir(folder_full_path)
                    files = glob.glob("*.tif")
                    #Remove temp files
                    if settings.ignore_string != None:
                        files = [ x for x in files if settings.ignore_string not in x ]
                    shuffle(files)
                    #Parallel
                    #Get time
                    now = datetime.now()
                    #Get hour and run the alternative number of workers during the night
                    if now.hour > 17 and now.hour < 7:
                        pool = mp.Pool(settings.no_workers_night)
                    else:
                        pool = mp.Pool(settings.no_workers)
                    res = pool.starmap(process_tif, zip(files, repeat(folder_path), repeat(folder_id), repeat(folder_full_path), repeat(tmp_folder)))
                    pool.close()
                    #MD5
                    for file in glob.glob("*.md5"):
                        q_md5 = queries.update_folders_md5.format("tif", folder_id)
                        logger1.info(q_md5)
                        db_cursor.execute(q_md5)
                    with os.scandir(folder_path + "/" + settings.raw_files_path) as files:
                        folder_full_path = "{}/{}".format(folder_path, settings.raw_files_path)
                        os.chdir(folder_full_path)
                        for file in files:
                            if settings.ignore_string not in file.name and file.is_file():
                                filename = file.name
                                #TIF Files
                                if Path(filename).suffix.lower() == '.{}'.format(settings.raw_files).lower():
                                    #If the file matches the raw extension
                                    process_raw(filename, folder_path, folder_id, settings.raw_files, folder_full_path, tmp_folder)
                                elif (Path(filename).suffix.lower() == ".md5"):
                                    #MD5 file
                                    q_md5 = queries.update_folders_md5.format("raw", folder_id)
                                    logger1.info(q_md5)
                                    db_cursor.execute(q_md5)
                    if 'jpg' in settings.project_checks:
                        with os.scandir(folder_path + "/" + settings.jpg_files_path) as files:
                            for file in files:
                                if settings.ignore_string not in file.name and file.is_file():
                                    filename = file.name
                                    if (Path(filename).suffix.lower() == ".md5"):
                                        #MD5 file
                                        q_md5 = queries.update_folders_md5.format("jpg", folder_id)
                                        logger1.info(q_md5)
                                        db_cursor.execute(q_md5)
            shutil.rmtree(tmp_folder, ignore_errors = True)
            folder_updated_at(folder_id, db_cursor)
    #Check for deleted files
    check_deleted()
    os.chdir(filecheck_dir)
    #Disconnect from db
    conn.close()
    logger1.info("Sleeping for {} secs".format(settings.sleep))
    #Sleep before trying again
    time.sleep(settings.sleep)



############################################
# Main loop
############################################

if __name__=="__main__":
    while True:
        try:
            main()
        except KeyboardInterrupt:
            logger1.info("Ctrl-c detected. Leaving program.")
            sys.exit(0)
        except Exception as e:
            logger1.error("There was an error: {}".format(e))
            sys.exit(1)



sys.exit(0)