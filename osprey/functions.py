#Functions for MDfilecheck.py

import os, subprocess, re, xmltodict
import settings
from random import randint
import queries
#For MD5
import hashlib
import glob
from PIL import Image
from subprocess import Popen,PIPE


def check_requirements(program):
    """
    Check if required programs are installed
    """
    #From https://stackoverflow.com/a/34177358
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
        folder_name = "{}/{}".format(server_folder_path[len_server_folder_path-2], server_folder_path[len_server_folder_path-1])
    db_cursor.execute(queries.select_folderid, {'project_folder': folder_name, 'project_id': project_id})
    folder_id = db_cursor.fetchone()
    if folder_id == None:
        #Folder does not exists, create
        db_cursor.execute(queries.new_folder, {'project_folder': folder_name, 'folder_path': folder_path, 'project_id': project_id})
        folder_id = db_cursor.fetchone()
    folder_date = settings.folder_date(folder_name)
    db_cursor.execute(queries.folder_date, {'datequery': folder_date, 'folder_id': folder_id[0]})
    return folder_id[0]



def delete_folder_files(folder_id, db_cursor, logger):
    db_cursor.execute(queries.del_folder_files, {'folder_id': folder_id})
    logger.info(db_cursor.query.decode("utf-8"))
    return True



def file_pair_check(file_id, filename, tif_path, file_tif, raw_path, file_raw, db_cursor, logger):
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
    logger.info(db_cursor.query.decode("utf-8"))
    return True


def folder_updated_at(folder_id, db_cursor):
    """
    Update the last time the folder was checked
    """
    db_cursor.execute(queries.folder_updated_at, {'folder_id': folder_id})
    return True



def file_updated_at(file_id, db_cursor):
    """
    Update the last time the file was checked
    """
    db_cursor.execute(queries.file_updated_at, {'file_id': file_id})
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
        db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'jhove', 'check_results': 1, 'check_info': error_msg})
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
    return True



def tif_compression(file_id, filename, db_cursor):
    """
    Check if the image has compression
    """
    p = subprocess.Popen(['exiftool', '-T', '-compression', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out,err) = p.communicate()
    compressed_info = out.decode('UTF-8').replace('\n','')
    if compressed_info == "LZW":
        f_compressed = 0
    else:
        f_compressed = 1
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'tif_compression', 'check_results': f_compressed, 'check_info': compressed_info})
    return True



def valid_name(file_id, filename, db_cursor, paranoid = False):
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
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'valid_name', 'check_results': filename_check, 'check_info': filename_check_info})
    return True



def tifpages(file_id, filename, db_cursor, paranoid = False):
    """
    Check if TIF has multiple pages
    """
    p = subprocess.Popen(['identify', '-format', '%n\\n', filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out,err) = p.communicate()
    try:
        if int(len(out.split())) == 1:
            pages_vals = 0
            no_pages = str(int(len(out.split()))) + " page"
        else:
            pages_vals = 1
            no_pages = str(int(len(out.split()))) + " pages"
    except:
        no_pages = "Unknown"
        pages_vals = 1
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'tifpages', 'check_results': pages_vals, 'check_info': no_pages})
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
    return True



def file_exif(file_id, filename, filetype, db_cursor):
    """
    Extract the EXIF info from the RAW file
    """
    p = subprocess.Popen(['exiftool', '-t', '-a', '-U', '-u', '-D', '-G1', '-s',  filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out,err) = p.communicate()
    if p.returncode == 0:
        exif_read = 0
    else:
        exif_read = 1
    exif_info = out
    for line in exif_info.splitlines():
        tag = re.split(r'\t+', line.decode('UTF-8'))
        db_cursor.execute(queries.save_exif, {'file_id': file_id, 'filetype': filetype, 'taggroup': tag[0], 'tagid': tag[1], 'tag': tag[2], 'value': tag[3]})
    return True



def itpc_validate(file_id, filename, db_cursor):
    """
    Check the IPTC Metadata
    Need to rewrite 
    """
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
    return True



def file_size_check(filename, filetype, file_id, db_cursor):
    """
    Check if a file is within the size limits
    """
    file_size = os.path.getsize(filename)
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
    return True



def delete_folder_files(folder_id, db_cursor):
    db_cursor.execute(queries.del_folder_files, {'folder_id': folder_id})
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



def checkmd5file(md5_file, folder_id, filetype, db_cursor):
    """
    Check if md5 hashes match with the files
    -In progress
    """
    md5_error = ""
    if filetype == "tif":
        db_cursor.execute(queries.select_tif_md5, {'folder_id': folder_id})
    elif filetype == "raw":
        db_cursor.execute(queries.select_raw_md5, {'folder_id': folder_id})
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



def jpgpreview(file_id, filename):
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
    try:
        p = subprocess.run(['convert', "{}[0]".format(filename), '-resize', '1000x1000', preview_image], stdout=PIPE,stderr=PIPE)
        return True
    except:
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
    db_cursor.execute(queries.file_check, {'file_id': file_id, 'file_check': 'raw_pair', 'check_results': file_pair, 'check_info': file_pair_info})
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
    if magick_return:
        #Store MD5
        file_md5 = filemd5(filename)
        db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'jpg', 'md5': file_md5})
    return True




def soxi_check(file_id, filename, file_check, expected_val, db_cursor, loggerfile):
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
    loggerfile.info(db_cursor.query.decode("utf-8"))
    return True




def check_jpg(file_id, filename, db_cursor, loggerfile):
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
    loggerfile.info(db_cursor.query.decode("utf-8"))
    if magick_return:
        #Store MD5
        file_md5 = filemd5(filename)
        db_cursor.execute(queries.save_md5, {'file_id': file_id, 'filetype': 'jpg', 'md5': file_md5})
        loggerfile.info(db_cursor.query.decode("utf-8"))
    return True



def checkmd5file(md5_file, folder_id, filetype, db_cursor, loggerfile):
    """
    Check if md5 hashes match with the files
    -In progress
    """
    md5_error = ""
    if filetype == "tif":
        db_cursor.execute(queries.select_tif_md5, {'folder_id': folder_id, 'filetype': 'tif'})
    elif filetype == "raw":
        db_cursor.execute(queries.select_tif_md5, {'folder_id': folder_id, 'filetype': 'raw'})
    loggerfile.info(db_cursor.query.decode("utf-8"))
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





def check_deleted(filetype, db_cursor, loggerfile):
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
    db_cursor.execute(queries.get_files, {'project_id': settings.project_id})
    loggerfile.info(db_cursor.query.decode("utf-8"))
    files = db_cursor.fetchall()
    for file in files:
        if os.path.isfile("{}/{}/{}.{}".format(file[2], files_path, file[1], filetype)) == True:
            file_exists = 0
            file_exists_info = "File {}/{}/{}.{} was found".format(file[2], files_path, file[1], filetype)
        else:
            file_exists = 1
            file_exists_info = "File {}/{}/{}.{} was not found".format(file[2], files_path, file[1], filetype)
        db_cursor.execute(queries.file_check, {'file_id': file[0], 'file_check': 'file_exists', 'check_results': file_exists, 'check_info': file_exists_info})
        loggerfile.info(db_cursor.query.decode("utf-8"))
    return True




def check_stitched_jpg(file_id, filename, db_cursor, loggerfile):
    """
    Run checks for jpg files that were stitched from 2 images
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





def jpgpreview(file_id, filename, loggerfile):
    """
    Create preview image
    """
    if settings.jpg_previews == "":
        loggerfile.error("JPG preview folder is not set in settings file")
        return False
    preview_file_path = "{}/{}".format(settings.jpg_previews, str(file_id)[0:2])
    preview_image = "{}/{}.jpg".format(preview_file_path, file_id)
    #Create subfolder if it doesn't exists
    if not os.path.exists(preview_file_path):
        os.makedirs(preview_file_path)
    #Delete old image, if exists
    if os.path.isfile(preview_image):
        im = Image.open(filename)
        width, height = im.size
        if width != settings.previews_size and height != settings.previews_size:
            #Size in settings changed, create new image
            os.remove(preview_image)
        else:
            loggerfile.info("JPG preview {} exists".format(preview_image))
            return True
    loggerfile.info("creating preview_image:{}".format(preview_image))
    if settings.previews_size == "full":
        p = subprocess.Popen(['convert', '-quiet', "{}[0]".format(filename), preview_image], stdout=PIPE, stderr=PIPE)
    else:
        p = subprocess.Popen(['convert', '-quiet', "{}[0]".format(filename), '-resize', '{imgsize}x{imgsize}'.format(imgsize = settings.previews_size), preview_image], stdout=PIPE, stderr=PIPE)
    out = p.communicate()
    if os.path.isfile(preview_image):
        loggerfile.info(out)
        return True
    else:
        loggerfile.error("File:{}|msg:{}".format(filename, out))
        return False


