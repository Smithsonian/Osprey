#!/usr/bin/env python3
#
# Osprey script 
#
# Validate products from a vendor, usually images
# Version 0.5.2
#
############################################
# Import modules
############################################
import os, sys, shutil, subprocess, locale, logging, glob
import xmltodict, bitmath, pandas, time, glob
#import exifread
from random import randint
#For Postgres
import psycopg2
#For MD5
import hashlib
from time import localtime, strftime
from pathlib import Path
from subprocess import Popen,PIPE
from datetime import datetime



##Set locale
locale.setlocale(locale.LC_ALL, 'en_US.utf8')

##Import queries from queries.py file
import queries

##Import helper functions
from functions import *


##Import settings from settings.py file
import settings


##Save current directory
filecheck_dir = os.getcwd()



############################################
# Logging
############################################
if not os.path.exists('{}/logs'.format(filecheck_dir)):
    os.makedirs('{}/logs'.format(filecheck_dir))
current_time = strftime("%Y%m%d%H%M%S", localtime())
logfile_name = '{}.log'.format(current_time)
logfile = '{filecheck_dir}/logs/{logfile_name}'.format(filecheck_dir = filecheck_dir, logfile_name = logfile_name)
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
logger1 = logging.getLogger("filecheck")



############################################
# Check requirements
############################################
if check_requirements(settings.jhove_path) == False:
    logger1.error("JHOVE was not found")
    sys.exit(1)
if check_requirements('identify') == False:
    logger1.error("Imagemagick was not found")
    sys.exit(1)
if check_requirements('soxi') == False:
    logger1.error("SoX was not found")
    sys.exit(1)



############################################
# Functions
############################################
def process_tif(filename, folder_path, folder_id, folder_full_path, db_cursor):
    """
    Run checks for tif files
    """
    folder_id = int(folder_id)
    tmp_folder = "{}/mdpp_{}".format(settings.tmp_folder, str(folder_id))
    if os.path.isdir(tmp_folder) == False:
        os.mkdir(tmp_folder)
    #Check if file exists, insert if not
    logger1.info("TIF file {}".format(filename))
    filename_stem = Path(filename).stem
    db_cursor.execute(queries.select_file_id, {'file_name': filename_stem, 'folder_id': folder_id})
    logger1.info(db_cursor.query.decode("utf-8"))
    file_id = db_cursor.fetchone()
    if file_id == None:
        #Get modified date for file
        file_timestamp_float = os.path.getmtime("{}/{}/{}".format(folder_path, settings.tif_files_path, filename))
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        db_cursor.execute(queries.insert_file, {'file_name': filename_stem, 'folder_id': folder_id, 'file_timestamp': file_timestamp})
        logger1.info(db_cursor.query.decode("utf-8"))
        file_id = db_cursor.fetchone()[0]
    else:
        file_id = file_id[0]
    print("file_id: {}".format(file_id))
    #Check if file is OK
    file_checks = 0
    for filecheck in settings.project_file_checks:
        db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': filecheck})
        logger1.info(db_cursor.query.decode("utf-8"))
        result = db_cursor.fetchone()
        if result == None:
            logger1.info("file_id:{};file_checks:{};result:None".format(file_id, filecheck))
            db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': filecheck, 'check_results': 9, 'check_info': ''})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = 1
        else:
            logger1.info("file_id:{};file_checks:{};result:{}".format(file_id, filecheck, result[0]))
            result = result[0]
            if result == 9:
                result = 1
        file_checks = file_checks + result
    #Check if MD5 is stored
    db_cursor.execute(queries.select_file_md5, {'file_id': file_id, 'filetype': 'tif'})
    logger1.info(db_cursor.query.decode("utf-8"))
    result = db_cursor.fetchone()
    if result == None: 
        logger1.info("file_id:{};file_checks:{};result:None".format(file_id, 'md5'))
        file_checks = file_checks + 1
    if file_checks == 0:
        file_updated_at(file_id, db_cursor)
        logger1.info("File with ID {} is OK, skipping".format(file_id))
        # #Disconnect from db
        # db_cursor.close()
        # conn2.close()
        return True
    else:
        logger1.info("file_checks: {} file_id: {}".format(file_checks, file_id))
        ##Checks that do not need a local copy
        if 'raw_pair' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'raw_pair'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #FilePair check
                pair_check = file_pair_check(file_id, filename, "{}/{}".format(folder_path, settings.tif_files_path), 'tif', "{}/{}".format(folder_path, settings.raw_files_path), settings.raw_files, db_cursor)
                logger1.info("pair_check:{}".format(pair_check))
                file_md5 = filemd5("{}/{}.{}".format("{}/{}".format(folder_path, settings.raw_files_path), filename_stem, settings.raw_files))
                db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'raw', 'md5': file_md5})
                logger1.info(db_cursor.query.decode("utf-8"))
                file_checks = file_checks - 1
        if file_checks == 0:
            return True
        if 'valid_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'valid_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #valid name in file
                valid_name(file_id, local_tempfile, db_cursor)
                file_checks = file_checks - 1
        if file_checks == 0:
            return True
        if 'unique_file' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'unique_file'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                db_cursor.execute(queries.check_unique, {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id})
                logger1.info(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchone()
                if result[0] > 0:
                    unique_file = 1
                else:
                    unique_file = 0
                db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'unique_file', 'check_results': unique_file, 'check_info': ''})
                logger1.info(db_cursor.query.decode("utf-8"))
                file_checks = file_checks - 1
        if file_checks == 0:
            return True
        if 'old_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                db_cursor.execute(queries.check_unique_old, {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id})
                logger1.info(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchall()
                if len(result) > 0:
                    old_name = 1
                    folders = ",".join(result[0])
                else:
                    old_name = 0
                    folders = ""
                db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'old_name', 'check_results': old_name, 'check_info': folders})
                logger1.info(db_cursor.query.decode("utf-8"))
                file_checks = file_checks - 1
        if file_checks == 0:
            return True
        ##Checks that DO need a local copy
        logger1.info("file_checks: {}".format(file_checks))
        logger1.info("Copying file {} to local tmp".format(filename))
        #Copy file to tmp folder
        local_tempfile = "{}/{}".format(tmp_folder, filename)
        try:
            shutil.copyfile("{}/{}/{}".format(folder_path, settings.tif_files_path, filename), local_tempfile)
        except:
            logger1.error("Could not copy file {}/{} to local tmp".format(folder_path, filename))
            db_cursor.execute(queries.file_exists, {'file_exists': 1, 'file_id': file_id})
            logger1.info(db_cursor.query.decode("utf-8"))
            return False
        #Compare MD5 between source and copy
        db_cursor.execute(queries.select_file_md5, {'file_id': file_id, 'filetype': 'tif'})
        logger1.info(db_cursor.query.decode("utf-8"))
        result = db_cursor.fetchone()
        if result == None:
            logger1.info("Getting MD5")
            sourcefile_md5 = filemd5("{}/{}/{}".format(folder_path, settings.tif_files_path, filename))
            #Store MD5
            file_md5 = filemd5(local_tempfile)
            if sourcefile_md5 != file_md5:
                logger1.error("MD5 hash of local copy does not match the source: {} vs {}".format(sourcefile_md5, file_md5))
                return False
            db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'tif', 'md5': file_md5})
            logger1.info(db_cursor.query.decode("utf-8"))
            logger1.info("tif_md5:{}".format(file_md5))
        if 'jhove' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'jhove'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #JHOVE check
                jhove_validate(file_id, local_tempfile, db_cursor)
        if 'itpc' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'itpc'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #ITPC Metadata
                itpc_validate(file_id, filename, db_cursor)
        if 'tif_size' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tif_size'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #File size check
                file_size_check(local_tempfile, "tif", file_id, db_cursor)
        if 'magick' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'magick'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #Imagemagick check
                magick_validate(file_id, local_tempfile, db_cursor)
        if 'jpg' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'jpg'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #JPG check
                check_jpg(file_id, "{}/{}/{}.jpg".format(folder_path, settings.jpg_files_path, filename_stem), db_cursor)
        if 'tifpages' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tifpages'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #check if tif has multiple pages
                tifpages(file_id, local_tempfile, db_cursor)
        #Generate jpg preview
        jpg_prev = jpgpreview(file_id, local_tempfile)
        logger1.info("jpg_prev:{}".format(jpg_prev))
        file_updated_at(file_id, db_cursor)
        #Disconnect from db
        # db_cursor.close()
        # conn2.close()
        os.remove(local_tempfile)
        return True



def process_wav(filename, folder_path, folder_id, db_cursor):
    """
    Run checks for wav files
    """
    folder_id = int(folder_id)
    tmp_folder = "{}/mdpp_wav_{}".format(settings.tmp_folder, str(folder_id))
    if os.path.isdir(tmp_folder):
        shutil.rmtree(tmp_folder, ignore_errors = True)
    os.mkdir(tmp_folder)
    filename_stem = Path(filename).stem
    #Check if file exists, insert if not
    logger1.info("WAV file {}".format(filename))
    q_checkfile = queries.select_file_id.format(filename_stem, folder_id)
    logger1.info(q_checkfile)
    db_cursor.execute(q_checkfile)
    file_id = db_cursor.fetchone()
    if file_id == None:
        file_timestamp_float = os.path.getmtime("{}/{}".format(folder_path, filename))
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        db_cursor.execute(queries.insert_file, {'file_name': filename_stem, 'folder_id': folder_id, 'unique_file': unique_file, 'file_timestamp': file_timestamp})
        logger1.info(db_cursor.query.decode("utf-8"))
        file_id = db_cursor.fetchone()[0]
    else:
        file_id = file_id[0]
    logger1.info("filename: {} with file_id {}".format(filename_stem, file_id))
    #Check if file is OK
    file_checks = 0
    for filecheck in settings.project_file_checks:
        db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': filecheck})
        logger1.info(db_cursor.query.decode("utf-8"))
        result = db_cursor.fetchone()
        if result[0] != None:
            file_checks = file_checks + result[0]
    if file_checks == 0:
        file_updated_at(file_id, db_cursor)
        logger1.info("File with ID {} is OK, skipping".format(file_id))
        # #Disconnect from db
        # db_cursor.close()
        # conn2.close()
        return True
    else:
        ##Checks that do not need a local copy
        if 'valid_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                valid_name(file_id, local_tempfile, db_cursor)
        if 'unique_file' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                db_cursor.execute(queries.check_unique, {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id})
                logger1.info(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchone()
                if result[0] > 0:
                    unique_file = 1
                else:
                    unique_file = 0
                db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'unique_file', 'check_results': unique_file, 'check_info': ''})
                logger1.info(db_cursor.query.decode("utf-8"))
        if 'old_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                db_cursor.execute(queries.check_unique_old, {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id})
                logger1.info(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchall()
                if len(result) > 0:
                    old_name = 1
                    folders = ",".join(result[0])
                else:
                    old_name = 0
                    folders = ""
                db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'old_name', 'check_results': old_name, 'check_info': folders})
                logger1.info(db_cursor.query.decode("utf-8"))
        ##Checks that DO need a local copy
        logger1.info("Copying file {} to local tmp".format(filename))
        #Copy file to tmp folder
        local_tempfile = "{}/{}".format(tmp_folder, filename)
        try:
            shutil.copyfile("{}/{}/{}".format(folder_path, wav_files_path, filename), local_tempfile)
        except:
            logger1.error("Could not copy file {}/{} to local tmp".format(folder_path, filename))
            db_cursor.execute(queries.file_exists, {'file_exists': 1, 'file_id': file_id})
            logger1.info(db_cursor.query.decode("utf-8"))
            return False
        #Compare MD5 between source and copy
        sourcefile_md5 = filemd5("{}/{}".format(folder_path, filename))
        #Store MD5
        file_md5 = filemd5(local_tempfile)
        if sourcefile_md5 != file_md5:
            logger1.error("MD5 hash of local copy does not match the source: {} vs {}".format(sourcefile_md5, file_md5))
            return False
        db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'wav', 'md5': file_md5})
        logger1.info(db_cursor.query.decode("utf-8"))
        logger1.info("wav_md5:{}".format(file_md5))
        if 'filetype' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                soxi_check(file_id, filename, "filetype", settings.wav_filetype, db_cursor)
        if 'samprate' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                soxi_check(file_id, filename, "samprate", settings.wav_samprate, db_cursor)
        if 'channels' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                soxi_check(file_id, filename, "channels", settings.wav_channels, db_cursor)
        if 'bits' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                soxi_check(file_id, filename, "bits", settings.wav_bits, db_cursor)
        if 'jhove' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            logger1.info(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                jhove_validate(file_id, local_tempfile, tmp_folder, db_cursor)
        file_updated_at(file_id, db_cursor)
        #Disconnect from db
        # db_cursor.close()
        # conn2.close()
        os.remove(local_tempfile)
        return True







def check_requirements(program):
    """
    Check if required programs are installed
    """
    #From https://stackoverflow.com/a/34177358
    from shutil import which 
    return which(program) is not None



def compress_log(filecheck_dir, logfile_name):
    """
    Check if a folder exists, add if it does not
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
        folder_name = "{}/{}".format(server_folder_path[len_server_folder_path-2], server_folder_path[len_server_folder_path-1])
    db_cursor.execute(queries.select_folderid, {'project_folder': folder_name, 'project_id': project_id})
    logger1.info(db_cursor.query.decode("utf-8"))
    folder_id = db_cursor.fetchone()
    if folder_id == None:
        #Folder does not exists, create
        db_cursor.execute(queries.new_folder, {'project_folder': folder_name, 'folder_path': folder_path, 'project_id': project_id})
        logger1.info(db_cursor.query.decode("utf-8"))
        folder_id = db_cursor.fetchone()
        logger1.info("folder_id:{}".format(folder_id[0]))
    # if settings.folder_date != "":
    #     folder_date = folder_path.split(settings.folder_date)[1]
    #     folder_date = "{}-{}-{}".format(folder_date[0:4], folder_date[4:6], folder_date[6:8])
    #     #Update to set date of folder
    #     db_cursor.execute(queries.folder_date, {'datequery': folder_date, 'folder_id': folder_id[0]})
    #     logger1.info(db_cursor.query.decode("utf-8"))
    folder_date = settings.folder_date(folder_name)
    db_cursor.execute(queries.folder_date, {'datequery': folder_date, 'folder_id': folder_id[0]})
    logger1.info(db_cursor.query.decode("utf-8"))
    return folder_id[0]



def folder_updated_at(folder_id, db_cursor):
    """
    Update the last time the folder was checked
    """
    db_cursor.execute(queries.folder_updated_at, {'folder_id': folder_id})
    logger1.info(db_cursor.query.decode("utf-8"))
    return True



def file_updated_at(file_id, db_cursor):
    """
    Update the last time the file was checked
    """
    db_cursor.execute(queries.file_updated_at, {'file_id': file_id})
    logger1.info(db_cursor.query.decode("utf-8"))
    return True



def jhove_validate(file_id, filename, db_cursor):
    """
    Validate the file with JHOVE
    """
    #Where to write the results
    xml_file = "{}/mdpp_{}.xml".format(settings.tmp_folder, randint(100, 100000))
    if os.path.isfile(xml_file):
        os.unlink(xml_file)
    #Run JHOVE
    subprocess.run([settings.jhove_path, "-h", "xml", "-o", xml_file, filename])
    #Open and read the results xml
    try:
        with open(xml_file) as fd:
            doc = xmltodict.parse(fd.read())
    except:
        error_msg = "Could not find result file from JHOVE ({})".format(xml_file)
        logger1.error(error_msg)
        db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'jhove', 'check_results': 1, 'check_info': error_msg})
        logger1.info(db_cursor.query.decode("utf-8"))
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
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'jhove', 'check_results': jhove_val, 'check_info': file_status})
    logger1.info(db_cursor.query.decode("utf-8"))
    return True



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
    else:
        magick_identify = 1
    magick_identify_info = out + err
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'magick', 'check_results': magick_identify, 'check_info': magick_identify_info.decode('UTF-8')})
    logger1.info(db_cursor.query.decode("utf-8"))
    return True



def valid_name(file_id, filename, db_cursor, paranoid = False):
    """
    Check if filename in database of accepted names
    """
    filename_stem = Path(filename).stem
    db_cursor.execute(settings.filename_pattern_query.format(filename_stem))
    valid_names = db_cursor.fetchone()[0]
    if valid_names == 0:
        filename_check = 1
        filename_check_info = "Filename {} not in list".format(filename_stem)
    else:
        filename_check = 0
        filename_check_info = "Filename {} in list".format(filename_stem)
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'valid_name', 'check_results': filename_check, 'check_info': filename_check_info})
    logger1.info(db_cursor.query.decode("utf-8"))
    return True



def tifpages(file_id, filename, db_cursor, paranoid = False):
    """
    Check if TIF has multiple pages
    """
    p = subprocess.Popen(['identify', '-quiet', '-format', '%p', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out,err) = p.communicate()
    try:
        if len(out) == 1:
            pages_vals = 0
            no_pages = str(len(out)) + " page"
        else:
            pages_vals = 1
            no_pages = str(len(out)) + " pages"
    except:
        no_pages = "Unknown"
        pages_vals = 1
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'tifpages', 'check_results': pages_vals, 'check_info': no_pages})
    logger1.info(db_cursor.query.decode("utf-8"))
    return True



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
    else:
        #Unkown check
        return False
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
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': file_check, 'check_results': result_code, 'check_info': result})
    logger1.info(db_cursor.query.decode("utf-8"))
    return True



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
        file_check = 'tif_size'
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
        file_check = 'raw_size'
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': file_check, 'check_results': result_code, 'check_info': result})
    logger1.info(db_cursor.query.decode("utf-8"))
    return True



def delete_folder_files(folder_id, db_cursor):
    db_cursor.execute(queries.del_folder_files, {'folder_id': folder_id})
    logger1.info(db_cursor.query.decode("utf-8"))
    return True



def filemd5(filepath):
    """
    Get MD5 hash of a file
    """
    md5_hash = hashlib.md5()
    with open(filepath, "rb") as f:
        # Read and update hash in chunks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
    file_md5 = md5_hash.hexdigest()
    return file_md5



def checkmd5file(md5_file, folder_id, filetype, db_cursor):
    """
    Check if md5 hashes match with the files
    -In progress
    """
    md5_error = ""
    if filetype == "tif":
        db_cursor.execute(queries.select_tif_md5, {'folder_id': folder_id, 'filetype': 'tif'})
    elif filetype == "raw":
        db_cursor.execute(queries.select_tif_md5, {'folder_id': folder_id, 'filetype': 'raw'})
    logger1.info(db_cursor.query.decode("utf-8"))
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



def check_deleted(filetype = 'tif'):
    """
    Deleted files are tagged in the database
    """
    #Connect to the database
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
    try:
        logger1.info("Connecting to database")
        con = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, password = settings.db_password, connect_timeout = 60)
    except:
        logger1.error("Could not connect to server.")
        sys.exit(1)
    con.autocommit = True
    db_cursor = con.cursor()
    db_cursor.execute(queries.get_files, {'project_id': settings.project_id})
    logger1.info(cur.query)
    files = db_cursor.fetchall()
    for file in files:
        if os.path.isfile("{}/{}/{}.{}".format(file[2], files_path, file[1], filetype)) == True:
            file_exists = 0
            file_exists_info = "File {}/{}/{}.{} was found".format(file[2], files_path, file[1], filetype)
        else:
            file_exists = 1
            file_exists_info = "File {}/{}/{}.{} was not found".format(file[2], files_path, file[1], filetype)
        db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'file_exists', 'check_results': file_exists, 'check_info': file_exists_info})
        logger1.info(db_cursor.query.decode("utf-8"))
    con.close()
    return True



def jpgpreview(file_id, filename):
    """
    Create preview image
    """
    if settings.jpg_previews == "":
        logger1.error("JPG preview folder is not set in settings file")
    preview_file_path = "{}/{}".format(settings.jpg_previews, str(file_id)[0:2])
    preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
    #Create subfolder if it doesn't exists
    if not os.path.exists(preview_file_path):
        os.makedirs(preview_file_path)
    #Delete old image, if exists
    if os.path.isfile(preview_image):
        logger1.info("JPG preview {} exists".format(preview_image))
        return True
    logger1.info("creating preview_image:{}".format(preview_image))
    if settings.previews_size == "full":
        p = subprocess.Popen(['convert', "{}[0]".format(filename), preview_image], stdout=PIPE, stderr=PIPE)
    else:
        p = subprocess.Popen(['convert', "{}[0]".format(filename), '-resize', '{imgsize}x{imgsize}'.format(imgsize = settings.previews_size), preview_image], stdout=PIPE, stderr=PIPE)
    if p.returncode == 0:
        return True
    else:
        return False



def file_pair_check(file_id, filename, tif_path, file_tif, raw_path, file_raw, db_cursor):
    """
    Check if a file has a pair (tif + raw)
    """
    #base_filename = Path(filename).name
    #path_filename = Path(filename).parent
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
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'raw_pair', 'check_results': file_pair, 'check_info': file_pair_info})
    logger1.info(db_cursor.query.decode("utf-8"))
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
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'jpg', 'check_results': magick_identify, 'check_info': magick_identify_info.decode("utf-8").replace("'", "''")})
    logger1.info(db_cursor.query.decode("utf-8"))
    if magick_return:
        #Store MD5
        file_md5 = filemd5(filename)
        db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'jpg', 'md5': file_md5})
        logger1.info(db_cursor.query.decode("utf-8"))
    return True




def main():
    #Check that the paths are mounted
    for p_path in settings.project_paths:
        if os.path.ismount(p_path) == False:
            logger1.error("Path not found: {}".format(p_path))
            continue
    #Connect to the database
    logger1.info("Connecting to database")
    conn = psycopg2.connect(
                host = settings.db_host, 
                    database = settings.db_db, 
                    user = settings.db_user, 
                    connect_timeout = 60)
    conn.autocommit = True
    db_cursor = conn.cursor()
    #Update project
    db_cursor.execute(queries.update_projectchecks, {'project_file_checks': ','.join(settings.project_file_checks), 'project_id': settings.project_id})
    logger1.info(db_cursor.query.decode("utf-8"))
    #Run in each project path
    for project_path in settings.project_paths:
        logger1.info('project_path: {}'.format(project_path))
        #Generate list of folders in the path
        folders = []
        for entry in os.scandir(project_path):
            if entry.is_dir():
                folders.append(entry.path)
        #No folders found
        if len(folders) == 0:
            continue
        #Run each folder
        for folder in folders:
            folder_path = folder
            logger1.info(folder_path)
            folder_name = os.path.basename(folder)
            #Check if the folder exists in the database
            folder_id = check_folder(folder_name, folder_path, settings.project_id, db_cursor)
            if folder_id == None:
                logger1.error("Folder {} had an error".format(folder_name))
                continue
            os.chdir(folder_path)
            files = glob.glob("*.wav")
            logger1.info("Files in {}: {}".format(folder_path, ','.join(files)))
            logger1.info(files)
            #Remove temp files
            if settings.ignore_string != None:
                files = [ x for x in files if settings.ignore_string not in x ]
                logger1.info("Files without ignored strings in {}: {}".format(folder_path, ','.join(files)))
            ###########################
            #WAV files
            ###########################
            if settings.project_type == 'wav':
                #Check each wav file
                for file in files:
                    logger1.info("Running checks on file {}".format(file))
                    process_wav(file, folder_path, folder_id, folder_path, db_cursor)
                #MD5
                if len(glob.glob1("*.md5")) == 1:
                    db_cursor.execute(queries.update_folders_md5, {'folder_id': folder_id, 'filetype': 'wav', 'md5': 0})
                    logger1.info(db_cursor.query.decode("utf-8"))
                #Check for deleted files
                check_deleted('wavs')
            ###########################
            #TIF Files
            ###########################
            elif settings.project_type == 'tif':
                if (os.path.isdir(folder_path + "/" + settings.raw_files_path) == False and os.path.isdir(folder_path + "/" + settings.tif_files_path) == False):
                    logger1.info("Missing TIF and RAW folders")
                    db_cursor.execute(queries.update_folder_status9, {'error_info': "Missing TIF and RAW folders", 'folder_id': folder_id})
                    logger1.info(db_cursor.query.decode("utf-8"))
                    delete_folder_files(folder_id, db_cursor)
                    continue
                elif os.path.isdir(folder_path + "/" + settings.tif_files_path) == False:
                    logger1.info("Missing TIF folder")
                    db_cursor.execute(queries.update_folder_status9, {'error_info': "Missing TIF folder", 'folder_id': folder_id})
                    logger1.info(db_cursor.query.decode("utf-8"))
                    delete_folder_files(folder_id, db_cursor)
                    continue
                elif os.path.isdir(folder_path + "/" + settings.raw_files_path) == False:
                    logger1.info("Missing RAW folder")
                    db_cursor.execute(queries.update_folder_status9, {'error_info': "Missing RAW folder", 'folder_id': folder_id})
                    logger1.info(db_cursor.query.decode("utf-8"))
                    delete_folder_files(folder_id, db_cursor)
                    continue
                else:
                    logger1.info("Both folders present")
                    db_cursor.execute(queries.update_folder_0, {'folder_id': folder_id})
                    logger1.info(db_cursor.query.decode("utf-8"))
                    folder_full_path = "{}/{}".format(folder_path, settings.tif_files_path)
                    os.chdir(folder_full_path)
                    files = glob.glob("*.tif")
                    logger1.info(files)
                    #Remove temp files
                    if settings.ignore_string != None:
                        files = [ x for x in files if settings.ignore_string not in x ]
                        logger1.info("Files without ignored strings in {}: {}".format(folder_path, ','.join(files)))
                    for file in files:
                        logger1.info("Running checks on file {}".format(file))
                        process_tif(file, folder_path, folder_id, folder_full_path, db_cursor)
                    #MD5
                    db_cursor.execute(queries.update_folders_md5, {'folder_id': folder_id, 'filetype': 'tif', 'md5': 0})
                    logger1.info(db_cursor.query.decode("utf-8"))
                #Check for deleted files
                check_deleted('tifs')
            folder_updated_at(folder_id, db_cursor)
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
        #main()
        try:
            main()
        except KeyboardInterrupt:
            logger1.info("Ctrl-c detected. Leaving program.")
            compress_log(filecheck_dir, logfile_name)
            sys.exit(0)
        except Exception as e:
            logger1.error("There was an error: {}".format(e))
            compress_log(filecheck_dir, logfile_name)
            sys.exit(1)



sys.exit(0)
