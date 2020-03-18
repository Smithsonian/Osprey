#!/usr/bin/env python3
#
# Osprey script 
#
# Validate products from a vendor, usually images
#
############################################
# Import modules
############################################
import os, sys, shutil, subprocess, locale, logging, glob
import xmltodict, bitmath, pandas, time, glob
import random
#For Postgres
import psycopg2
from time import localtime, strftime
from pathlib import Path
from datetime import datetime


ver = "0.7.6"

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
# Check requirements
############################################
if check_requirements(settings.jhove_path) == False:
        print("JHOVE was not found")
        sys.exit(1)
if settings.project_type == 'wav':
    if check_requirements('soxi') == False:
        print("SoX was not found")
        sys.exit(1)
elif settings.project_type == 'tif':
    if check_requirements('identify') == False:
        print("Imagemagick was not found")
        sys.exit(1)
    if check_requirements('exiftool') == False:
        print("exiftool was not found")
        sys.exit(1)



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
#logging.getLogger('').addHandler(console)
logger1 = logging.getLogger("filecheck")
logging.getLogger('filecheck').addHandler(console)
logger1.info("osprey version {}".format(ver))



############################################
# Functions
############################################
def process_tif(filename, folder_path, folder_id, folder_full_path, db_cursor, loggerfile):
    """
    Run checks for tif files
    """
    folder_id = int(folder_id)
    tmp_folder = settings.tmp_folder
    #Check if file exists, insert if not
    #loggerfile.info("TIF file {}".format(filename))
    filename_stem = Path(filename).stem
    db_cursor.execute(queries.select_file_id, {'file_name': filename_stem, 'folder_id': folder_id})
    loggerfile.debug(db_cursor.query.decode("utf-8"))
    file_id = db_cursor.fetchone()
    if file_id == None:
        #Get modified date for file
        file_timestamp_float = os.path.getmtime("{}/{}/{}".format(folder_path, settings.tif_files_path, filename))
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        db_cursor.execute(queries.insert_file, {'file_name': filename_stem, 'folder_id': folder_id, 'file_timestamp': file_timestamp})
        loggerfile.debug(db_cursor.query.decode("utf-8"))
        file_id = db_cursor.fetchone()[0]
    else:
        file_id = file_id[0]
    print("file_id: {}".format(file_id))
    #Check if file is OK
    file_checks = 0
    for filecheck in settings.project_file_checks:
        db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': filecheck})
        result = db_cursor.fetchone()
        if result == None:
            db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': filecheck, 'check_results': 9, 'check_info': ''})
            result = 1
        else:
            result = result[0]
            if result == 9:
                result = 1
        file_checks = file_checks + result
    #Check if JPG preview exists
    preview_file_path = "{}/{}".format(settings.jpg_previews, str(file_id)[0:2])
    preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
    if os.path.isfile(preview_image) == False:
        loggerfile.info("jpg_preview {} does not exist for file_id:{}".format(preview_image, file_id))
        file_checks = file_checks + 1
    #Get filesize from TIF:
    file_size = os.path.getsize("{}/{}/{}.tif".format(folder_path, settings.tif_files_path, filename_stem))
    db_cursor.execute(queries.save_filesize, {'file_id': file_id, 'filetype': 'TIF', 'filesize': file_size})
    loggerfile.debug(db_cursor.query.decode("utf-8"))
    #Get filesize from RAW:
    if os.path.isfile("{}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem, settings.raw_files)):
        file_size = os.path.getsize("{}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem, settings.raw_files))
        db_cursor.execute(queries.save_filesize, {'file_id': file_id, 'filetype': 'RAW', 'filesize': file_size})
        loggerfile.debug(db_cursor.query.decode("utf-8"))
    #Get exif from TIF
    db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': 'TIF'})
    check_exif = db_cursor.fetchone()[0]
    loggerfile.debug("check_exif_tif: {}".format(check_exif))
    if check_exif == 0:
        file_checks = file_checks + 1
    #Check if MD5 is stored
    db_cursor.execute(queries.select_file_md5, {'file_id': file_id, 'filetype': 'tif'})
    loggerfile.debug(db_cursor.query.decode("utf-8"))
    result = db_cursor.fetchone()
    if result == None: 
        loggerfile.info("file_id:{};file_checks:{};result:None".format(file_id, 'md5'))
        file_checks = file_checks + 1
    if file_checks == 0:
        file_updated_at(file_id, db_cursor, loggerfile)
        loggerfile.info("File with ID {} is OK, skipping".format(file_id))
        return True
    else:
        loggerfile.info("file_checks: {} file_id: {}".format(file_checks, file_id))
        ##Checks that do not need a local copy
        if 'raw_pair' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'raw_pair'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #FilePair check
                pair_check = file_pair_check(file_id, filename, "{}/{}".format(folder_path, settings.tif_files_path), 'tif', "{}/{}".format(folder_path, settings.raw_files_path), settings.raw_files, db_cursor, loggerfile)
                loggerfile.info("pair_check:{}".format(pair_check))
                file_md5 = filemd5("{}/{}.{}".format("{}/{}".format(folder_path, settings.raw_files_path), filename_stem, settings.raw_files))
                db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'raw', 'md5': file_md5})
                loggerfile.debug(db_cursor.query.decode("utf-8"))
                file_checks = file_checks - 1
        if file_checks == 0:
            return True
        if 'valid_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'valid_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #valid name in file
                valid_name(file_id, local_tempfile, db_cursor, loggerfile)
                file_checks = file_checks - 1
        if file_checks == 0:
            return True
        if 'prefix' in settings.project_file_checks:
            if filename.startswith(settings.filename_prefix):
                prefix_check = 0
                prefix_info = ""
                file_checks = file_checks - 1
            else:
                prefix_check = 1
                prefix_info = "Filename doesn't start with the required prefix {}".format(settings.filename_prefix)
            db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'prefix', 'check_results': prefix_check, 'check_info': prefix_info})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
        if file_checks == 0:
            return True
        if 'unique_file' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'unique_file'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #Check in project
                db_cursor.execute(queries.check_unique, {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id, 'file_id': file_id})
                loggerfile.debug(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchall()
                if len(result) == 0:
                    unique_file = 0
                    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'unique_file', 'check_results': unique_file, 'check_info': ""})
                    loggerfile.debug(db_cursor.query.decode("utf-8"))
                    file_checks = file_checks - 1
                else:
                    unique_file = 1
                    for dupe in result:
                        db_cursor.execute(queries.not_unique, {'folder_id': dupe[1]})
                        loggerfile.debug(db_cursor.query.decode("utf-8"))
                        folder_dupe = db_cursor.fetchone()
                        db_cursor.execute(queries.file_check, {'file_id': dupe[0], 'file_check': 'unique_file', 'check_results': 1, 'check_info': "File with same name in {}".format(folder_path)})
                        loggerfile.debug(db_cursor.query.decode("utf-8"))
                        db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'unique_file', 'check_results': unique_file, 'check_info': "File with same name in {}".format(folder_dupe[0])})
                        loggerfile.debug(db_cursor.query.decode("utf-8"))
        if 'unique_file_all' in settings.project_file_checks:
            #Check in other projects
            db_cursor.execute(queries.check_unique_all, {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id, 'file_id': file_id})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()
            if result == None:
                unique_file = 0
                check_info = ""
            elif result[0] > 0:
                unique_file = 1
                db_cursor.execute(queries.not_unique_all, {'file_id': file_id, 'file_name': filename_stem, 'project_id': settings.project_id})
                loggerfile.debug(db_cursor.query.decode("utf-8"))
                folder_check = db_cursor.fetchone()
                folder_dupe = folder_check[0]
                alt_project_id = folder_check[1]
                check_info = "File with same name in {} of project {}".format(folder_check[0], folder_check[1])
                file_checks = file_checks - 1
            else:
                unique_file = 0
                check_info = ""
            db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'unique_file_all', 'check_results': unique_file, 'check_info': check_info})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
        if file_checks == 0:
            return True
        if 'old_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                db_cursor.execute(queries.check_unique_old, {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id})
                loggerfile.debug(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchall()
                if len(result) > 0:
                    old_name = 1
                    folders = ",".join(result[0])
                else:
                    old_name = 0
                    folders = ""
                db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'old_name', 'check_results': old_name, 'check_info': folders})
                loggerfile.debug(db_cursor.query.decode("utf-8"))
                file_checks = file_checks - 1
        if file_checks == 0:
            loggerfile.info("file_checks: {};skipping file {}".format(file_checks, file_id))
            return True
        ##Checks that DO need a local copy
        #Check if there is enough space first
        local_disk = shutil.disk_usage(settings.tmp_folder)
        if (local_disk.free/local_disk.total < 0.1):
            loggerfile.error("Disk is running out of space ({}%) - {}".format(round(local_disk.free/local_disk.total, 4) * 100, settings.tmp_folder))
            sys.exit(1)
        loggerfile.info("file_checks: {}".format(file_checks))
        loggerfile.info("Copying file {} to local tmp".format(filename))
        #Copy file to tmp folder
        local_tempfile = "{}/{}".format(tmp_folder, filename)
        #Check if file already exists
        if os.path.isfile(local_tempfile):
            os.remove(local_tempfile)
        try:
            shutil.copyfile("{}/{}/{}".format(folder_path, settings.tif_files_path, filename), local_tempfile)
        except:
            loggerfile.error("Could not copy file {}/{}/{} to local tmp".format(folder_path, settings.tif_files_path, filename))
            db_cursor.execute(queries.file_exists, {'file_exists': 1, 'file_id': file_id})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            sys.exit(1)
        #Generate jpg preview, if needed
        jpg_prev = jpgpreview(file_id, local_tempfile, loggerfile)
        #Compare MD5 between source and copy
        db_cursor.execute(queries.select_file_md5, {'file_id': file_id, 'filetype': 'tif'})
        loggerfile.debug(db_cursor.query.decode("utf-8"))
        result = db_cursor.fetchone()
        if result == None:
            loggerfile.info("Getting MD5")
            sourcefile_md5 = filemd5("{}/{}/{}".format(folder_path, settings.tif_files_path, filename))
            #Store MD5
            file_md5 = filemd5(local_tempfile)
            if sourcefile_md5 != file_md5:
                loggerfile.error("MD5 hash of local copy does not match the source: {} vs {}".format(sourcefile_md5, file_md5))
                return False
            db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'tif', 'md5': file_md5})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            loggerfile.info("tif_md5:{}".format(file_md5))
        if 'jhove' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'jhove'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #JHOVE check
                jhove_validate(file_id, local_tempfile, db_cursor, loggerfile)
        if 'itpc' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'itpc'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #ITPC Metadata
                itpc_validate(file_id, filename, db_cursor)
        if 'tif_size' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tif_size'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #File size check
                file_size_check(local_tempfile, "tif", file_id, db_cursor, loggerfile)
        if 'magick' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'magick'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #Imagemagick check
                magick_validate(file_id, local_tempfile, db_cursor, loggerfile)
        if 'jpg' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'jpg'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #JPG check
                check_jpg(file_id, "{}/{}/{}.jpg".format(folder_path, settings.jpg_files_path, filename_stem), db_cursor, loggerfile)
        if 'stitched_jpg' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'stitched_jpg'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #JPG check
                stitched_name = filename_stem.replace(settings.jpgstitch_original_1, settings.jpgstitch_new)
                stitched_name = stitched_name.replace(settings.jpgstitch_original_2, settings.jpgstitch_new)
                check_stitched_jpg(file_id, "{}/{}/{}.jpg".format(folder_path, settings.jpg_files_path, stitched_name), db_cursor, loggerfile)                
        if 'tifpages' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tifpages'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #check if tif has multiple pages
                tifpages(file_id, local_tempfile, db_cursor, loggerfile)
        if 'tif_compression' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'tif_compression'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                #check if tif is compressed
                tif_compression(file_id, local_tempfile, db_cursor, loggerfile)
        #Get exif from TIF
        db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': 'TIF'})
        check_exif = db_cursor.fetchone()[0]
        loggerfile.info("check_exif_tif: {}".format(check_exif))
        if check_exif == 0:
            loggerfile.info("Getting EXIF from {}/{}/{}.tif".format(folder_path, settings.tif_files_path, filename_stem))
            file_exif(file_id, local_tempfile, 'TIF', db_cursor, loggerfile)
        #Get exif from RAW
        db_cursor.execute(queries.check_exif, {'file_id': file_id, 'filetype': 'RAW'})
        check_exif = db_cursor.fetchone()[0]
        loggerfile.info("check_exif_raw: {}".format(check_exif))
        if check_exif == 0:
            if os.path.isfile("{}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem, settings.raw_files)):
                loggerfile.info("Getting EXIF from {}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem, settings.raw_files))
                file_exif(file_id, "{}/{}/{}.{}".format(folder_path, settings.raw_files_path, filename_stem, settings.raw_files), 'RAW', db_cursor, loggerfile)
        loggerfile.info("jpg_prev:{}".format(jpg_prev))
        if os.path.isfile(local_tempfile):
            os.remove(local_tempfile)
        file_updated_at(file_id, db_cursor, loggerfile)
        return True



def process_wav(filename, folder_path, folder_id, db_cursor, loggerfile):
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
    loggerfile.info("WAV file {}".format(filename))
    q_checkfile = queries.select_file_id.format(filename_stem, folder_id)
    loggerfile.info(q_checkfile)
    db_cursor.execute(q_checkfile)
    file_id = db_cursor.fetchone()
    if file_id == None:
        file_timestamp_float = os.path.getmtime("{}/{}".format(folder_path, filename))
        file_timestamp = datetime.fromtimestamp(file_timestamp_float).strftime('%Y-%m-%d %H:%M:%S')
        db_cursor.execute(queries.insert_file, {'file_name': filename_stem, 'folder_id': folder_id, 'unique_file': unique_file, 'file_timestamp': file_timestamp})
        loggerfile.debug(db_cursor.query.decode("utf-8"))
        file_id = db_cursor.fetchone()[0]
    else:
        file_id = file_id[0]
    loggerfile.info("filename: {} with file_id {}".format(filename_stem, file_id))
    #Check if file is OK
    file_checks = 0
    for filecheck in settings.project_file_checks:
        db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': filecheck})
        loggerfile.debug(db_cursor.query.decode("utf-8"))
        result = db_cursor.fetchone()
        if result[0] != None:
            file_checks = file_checks + result[0]
    if file_checks == 0:
        file_updated_at(file_id, db_cursor, loggerfile)
        loggerfile.info("File with ID {} is OK, skipping".format(file_id))
        return True
    else:
        ##Checks that do not need a local copy
        if 'valid_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                valid_name(file_id, local_tempfile, db_cursor, loggerfile)
        if 'unique_file' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                db_cursor.execute(queries.check_unique, {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id})
                loggerfile.debug(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchone()
                if result[0] > 0:
                    unique_file = 1
                else:
                    unique_file = 0
                db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'unique_file', 'check_results': unique_file, 'check_info': ''})
                loggerfile.debug(db_cursor.query.decode("utf-8"))
        if 'old_name' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                db_cursor.execute(queries.check_unique_old, {'file_name': filename_stem, 'folder_id': folder_id, 'project_id': settings.project_id})
                loggerfile.debug(db_cursor.query.decode("utf-8"))
                result = db_cursor.fetchall()
                if len(result) > 0:
                    old_name = 1
                    folders = ",".join(result[0])
                else:
                    old_name = 0
                    folders = ""
                db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'old_name', 'check_results': old_name, 'check_info': folders})
                loggerfile.debug(db_cursor.query.decode("utf-8"))
        ##Checks that DO need a local copy
        #Check if there is enough space first
        local_disk = shutil.disk_usage(settings.tmp_folder)
        if (local_disk.free/local_disk.total < 0.1):
            loggerfile.error("Disk is running out of space {} ({})".format(local_disk.free/local_disk.total, settings.tmp_folder))
            sys.exit(1)
        loggerfile.info("Copying file {} to local tmp".format(filename))
        #Copy file to tmp folder
        local_tempfile = "{}/{}".format(tmp_folder, filename)
        try:
            shutil.copyfile("{}/{}/{}".format(folder_path, wav_files_path, filename), local_tempfile)
        except:
            loggerfile.error("Could not copy file {}/{}/{} to local tmp".format(folder_path, wav_files_path, filename))
            db_cursor.execute(queries.file_exists, {'file_exists': 1, 'file_id': file_id})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            #return False
            sys.exit(1)
        #Compare MD5 between source and copy
        sourcefile_md5 = filemd5("{}/{}".format(folder_path, filename))
        #Store MD5
        file_md5 = filemd5(local_tempfile)
        if sourcefile_md5 != file_md5:
            loggerfile.error("MD5 hash of local copy does not match the source: {} vs {}".format(sourcefile_md5, file_md5))
            return False
        db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'wav', 'md5': file_md5})
        loggerfile.debug(db_cursor.query.decode("utf-8"))
        loggerfile.info("wav_md5:{}".format(file_md5))
        if 'filetype' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                soxi_check(file_id, filename, "filetype", settings.wav_filetype, db_cursor, loggerfile)
        if 'samprate' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                soxi_check(file_id, filename, "samprate", settings.wav_samprate, db_cursor, loggerfile)
        if 'channels' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                soxi_check(file_id, filename, "channels", settings.wav_channels, db_cursor, loggerfile)
        if 'bits' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                soxi_check(file_id, filename, "bits", settings.wav_bits, db_cursor, loggerfile)
        if 'jhove' in settings.project_file_checks:
            db_cursor.execute(queries.select_check_file, {'file_id': file_id, 'filecheck': 'old_name'})
            loggerfile.debug(db_cursor.query.decode("utf-8"))
            result = db_cursor.fetchone()[0]
            if result != 0:
                jhove_validate(file_id, local_tempfile, tmp_folder, db_cursor, loggerfile)
        file_updated_at(file_id, db_cursor, loggerfile)
        os.remove(local_tempfile)
        return True



def main():
    #Check that the paths are valid dirs and are mounted
    for p_path in settings.project_paths:
        if os.path.isdir(p_path) == False:
            logger1.error("Path not found: {}".format(p_path))
            sys.exit(1)
    #Connect to the database
    logger1.info("Connecting to database")
    conn = psycopg2.connect(host = settings.db_host, database = settings.db_db, user = settings.db_user, connect_timeout = 60)
    conn.autocommit = True
    db_cursor = conn.cursor()
    #Clear project shares
    db_cursor.execute(queries.remove_shares, {'project_id': settings.project_id})
    logger1.debug(db_cursor.query.decode("utf-8"))
    #Check project shares
    for share in settings.project_shares:
        logger1.info("Share: {} ({})".format(share[0], share[1]))
        share_disk = shutil.disk_usage(share[0])
        try:
            share_percent = round(share_disk.used/share_disk.total, 4) * 100
            db_cursor.execute(queries.update_share, {'project_id': settings.project_id, 'share': share[1], 'localpath': share[0], 'used': share_percent, 'total': share_disk.total})
            logger1.debug(db_cursor.query.decode("utf-8"))
        except:
            logger1.error("Error checking the share {}".format(share[0]))
            continue        
    #Update project
    db_cursor.execute(queries.update_projectchecks, {'project_file_checks': ','.join(settings.project_file_checks), 'project_id': settings.project_id})
    logger1.debug(db_cursor.query.decode("utf-8"))
    #Loop each project path
    for project_path in settings.project_paths:
        logger1.debug('project_path: {}'.format(project_path))
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
            #Check if folder is ready or in dams
            db_cursor.execute(queries.folder_in_dams, {'folder_id': folder_id})
            logger1.debug(db_cursor.query.decode("utf-8"))
            f_in_dams = db_cursor.fetchone()
            if f_in_dams[0] == 0 or f_in_dams[0] == 1:
                #Folder ready for dams or in dams already, skip
                logger1.info("Folder in DAMS, skipping {}".format(folder_path))
                continue
            #Check if another computer is processing the folder
            db_cursor.execute(queries.folder_check_processing, {'folder_id': folder_id})
            logger1.debug(db_cursor.query.decode("utf-8"))
            folder_proc = db_cursor.fetchone()
            if folder_proc[0] == True:
                logger1.info("Folder checked by another computer, going for the next one {}".format(folder_path))
                continue
            #Set as processing
            db_cursor.execute(queries.folder_processing_update, {'folder_id': folder_id, 'processing': 't'})
            logger1.debug(db_cursor.query.decode("utf-8"))
            os.chdir(folder_path)
            files = glob.glob("*.wav")
            random.shuffle(files)
            logger1.debug("Files in {}: {}".format(folder_path, ','.join(files)))
            logger1.info("{} files in {}".format(len(files), folder_path, ))
            #Remove files to ignore
            if settings.ignore_string != None:
                files = [ x for x in files if settings.ignore_string not in x ]
                logger1.debug("Files without ignored strings in {}: {}".format(folder_path, ','.join(files)))
            ###########################
            #WAV files
            ###########################
            if settings.project_type == 'wav':
                #Check each wav file
                for file in files:
                    logger1.info("Running checks on file {}".format(file))
                    process_wav(file, folder_path, folder_id, folder_path, db_cursor, logger1)
                #MD5
                if len(glob.glob1("*.md5")) == 1:
                    db_cursor.execute(queries.update_folders_md5, {'folder_id': folder_id, 'filetype': 'wav', 'md5': 0})
                    logger1.debug(db_cursor.query.decode("utf-8"))
                #Check for deleted files
                if settings.check_deleted == True:
                    check_deleted('wav', db_cursor, logger1)
            ###########################
            #TIF Files
            ###########################
            elif settings.project_type == 'tif':
                if (os.path.isdir(folder_path + "/" + settings.raw_files_path) == False and os.path.isdir(folder_path + "/" + settings.tif_files_path) == False):
                    logger1.info("Missing TIF and RAW folders")
                    db_cursor.execute(queries.update_folder_status9, {'error_info': "Missing TIF and RAW folders", 'folder_id': folder_id})
                    logger1.debug(db_cursor.query.decode("utf-8"))
                    delete_folder_files(folder_id, db_cursor, logger1)
                    continue
                elif os.path.isdir(folder_path + "/" + settings.tif_files_path) == False:
                    logger1.info("Missing TIF folder")
                    db_cursor.execute(queries.update_folder_status9, {'error_info': "Missing TIF folder", 'folder_id': folder_id})
                    logger1.debug(db_cursor.query.decode("utf-8"))
                    delete_folder_files(folder_id, db_cursor, logger1)
                    continue
                elif os.path.isdir(folder_path + "/" + settings.raw_files_path) == False:
                    logger1.info("Missing RAW folder")
                    db_cursor.execute(queries.update_folder_status9, {'error_info': "Missing RAW folder", 'folder_id': folder_id})
                    logger1.debug(db_cursor.query.decode("utf-8"))
                    delete_folder_files(folder_id, db_cursor, logger1)
                    continue
                else:
                    logger1.info("Both folders present")
                    db_cursor.execute(queries.update_folder_0, {'folder_id': folder_id})
                    logger1.debug(db_cursor.query.decode("utf-8"))
                    folder_full_path = "{}/{}".format(folder_path, settings.tif_files_path)
                    os.chdir(folder_full_path)
                    files = glob.glob("*.tif")
                    logger1.info(files)
                    #Remove temp files
                    if settings.ignore_string != None:
                        files = [ x for x in files if settings.ignore_string not in x ]
                        logger1.debug("Files without ignored strings in {}: {}".format(folder_path, ','.join(files)))
                    for file in files:
                        logger1.info("Running checks on file {}".format(file))
                        process_tif(file, folder_path, folder_id, folder_full_path, db_cursor, logger1)
                    #MD5
                    if len(glob.glob(folder_path + "/" + settings.tif_files_path + "/*.md5")) == 1:
                        db_cursor.execute(queries.update_folders_md5, {'folder_id': folder_id, 'filetype': 'tif', 'md5': 0})
                        logger1.debug(db_cursor.query.decode("utf-8"))
                    else:
                        db_cursor.execute(queries.update_folders_md5, {'folder_id': folder_id, 'filetype': 'tif', 'md5': 1})
                        logger1.debug(db_cursor.query.decode("utf-8"))
                    if len(glob.glob(folder_path + "/" + settings.raw_files_path + "/*.md5")) == 1:
                        db_cursor.execute(queries.update_folders_md5, {'folder_id': folder_id, 'filetype': 'raw', 'md5': 0})
                        logger1.debug(db_cursor.query.decode("utf-8"))
                    else:
                        db_cursor.execute(queries.update_folders_md5, {'folder_id': folder_id, 'filetype': 'raw', 'md5': 1})
                        logger1.debug(db_cursor.query.decode("utf-8"))
                #Check for deleted files
                if settings.check_deleted == True:
                    check_deleted('tif', db_cursor, logger1)
            folder_updated_at(folder_id, db_cursor, logger1)
            #Update folder stats
            update_folder_stats(folder_id, db_cursor, loggerfile)
            #Set as processing done
            db_cursor.execute(queries.folder_processing_update, {'folder_id': folder_id, 'processing': 'f'})
            logger1.debug(db_cursor.query.decode("utf-8"))
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
            print("Ctrl-c detected. Leaving program.")
            #Compress logs
            compress_log(filecheck_dir)
            sys.exit(0)
        except Exception as e:
            print("There was an error: {}".format(e))
            #Compress logs
            compress_log(filecheck_dir)
            sys.exit(1)



sys.exit(0)
