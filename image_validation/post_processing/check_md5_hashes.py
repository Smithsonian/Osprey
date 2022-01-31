

#TO DO

# MD5 files
if 'md5_hash' in settings.project_file_checks:
    folder_tif_md5 = None
    folder_raw_md5 = None
    if len(glob.glob(folder_path + "/" + settings.tif_files_path + "/*.md5")) == 1:
        db_cursor.execute(queries.update_folders_md5,
                          {'folder_id': folder_id, 'filetype': 'tif', 'md5': 0})
        folder_tif_md5 = True
        logger.debug(db_cursor.query.decode("utf-8"))
    else:
        db_cursor.execute(queries.update_folders_md5,
                          {'folder_id': folder_id, 'filetype': 'tif', 'md5': 1})
        folder_tif_md5 = False
        logger.debug(db_cursor.query.decode("utf-8"))
    if len(glob.glob(folder_path + "/" + settings.raw_files_path + "/*.md5")) == 1:
        db_cursor.execute(queries.update_folders_md5,
                          {'folder_id': folder_id, 'filetype': 'raw', 'md5': 0})
        folder_raw_md5 = True
        logger.debug(db_cursor.query.decode("utf-8"))
    else:
        db_cursor.execute(queries.update_folders_md5,
                          {'folder_id': folder_id, 'filetype': 'raw', 'md5': 1})
        folder_raw_md5 = False
        logger.debug(db_cursor.query.decode("utf-8"))
    # Check if md5 files match the hashes
    if folder_tif_md5 and folder_raw_md5:
        # Read .md5 files
        # Tifs md5
        tif_md5_file = glob.glob(folder_path + "/" + settings.tif_files_path + "/*.md5")[0]
        raw_md5_file = glob.glob(folder_path + "/" + settings.raw_files_path + "/*.md5")[0]
        md5_tif_hashes = pd.read_csv(tif_md5_file, sep=' ', header=None, names=['md5', 'file'])
        md5_raw_hashes = pd.read_csv(raw_md5_file, sep=' ', header=None, names=['md5', 'file'])
        db_cursor.execute(queries.get_folder_files, {'folder_id': folder_id})
        logger.debug(db_cursor.query.decode("utf-8"))
        files = db_cursor.fetchall()
        # No. of files match rows in md5 file
        if len(files) == len(md5_tif_hashes) and len(files) == len(md5_raw_hashes):
            for file in files:
                # TIF file
                db_cursor.execute(queries.select_file_md5,
                                  {'file_id': file['file_id'], 'filetype': 'TIF'})
                logger.debug(db_cursor.query.decode("utf-8"))
                file_md5_hash = db_cursor.fetchone()
                md5_from_file = md5_tif_hashes[md5_tif_hashes.file == file['filename']][
                    'md5'].to_string(
                    index=False).strip()
                if file_md5_hash[0] == md5_from_file:
                    md5_check_tif = 0
                else:
                    md5_check_tif = 1
                    md5_info_tif = "MD5 hash not matched for TIF"
                # RAW file
                db_cursor.execute(queries.select_file_md5,
                                  {'file_id': file['file_id'], 'filetype': 'RAW'})
                logger.debug(db_cursor.query.decode("utf-8"))
                file_md5_hash = db_cursor.fetchone()
                md5_from_file = md5_raw_hashes[md5_raw_hashes.file == file['filename']][
                    'md5'].to_string(
                    index=False).strip()
                if file_md5_hash[0] == md5_from_file:
                    md5_check_raw = 0
                else:
                    md5_check_raw = 1
                    md5_info_raw = "MD5 hash not matched for RAW"
                # Update database
                if md5_check_raw == 0 and md5_check_tif == 0:
                    db_cursor.execute(queries.file_check,
                                      {'file_id': file['file_id'], 'file_check': 'md5_hash',
                                       'check_results': 0,
                                       'check_info': md5_info})
                    logger.debug(db_cursor.query.decode("utf-8"))
                else:
                    db_cursor.execute(queries.file_check,
                                      {'file_id': file['file_id'], 'file_check': 'md5_hash',
                                       'check_results': 1,
                                       'check_info': '{} {}'.format(md5_info_tif, md5_info_raw)})
                    logger.debug(db_cursor.query.decode("utf-8"))