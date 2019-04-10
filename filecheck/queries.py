#Queries for MDfilecheck.py

select_folderid = "SELECT folder_id FROM folders WHERE project_folder='{}' and project_id = {}"

new_folder = "INSERT INTO folders (project_folder, path, status, md5_tif, md5_raw, md5_jpg, project_id) VALUES ('{}', '{}', 0, 9, 9, 9, {}) RETURNING folder_id"

folder_date = "UPDATE folders SET date = {} where project_id={}"

folder_updated_at = "UPDATE folders SET updated_at = NOW() where folder_id={}"

file_updated_at = "UPDATE files SET last_update = NOW() where file_id={}"

jhove = "UPDATE files SET jhove = {}, jhove_info = '{}' WHERE file_id = {}"

update_item_no = "UPDATE files SET item_no = {} WHERE file_id = {}"

magick = "UPDATE files SET magick = {}, magick_info = '{}' WHERE file_id = {}"

filepair = "UPDATE files SET file_pair = {}, file_pair_info = '{}' WHERE file_id = {}"

tif_size = "UPDATE files SET tif_size = {}, tif_size_info = '{}' WHERE file_id = {}"

raw_size = "UPDATE files SET raw_size = {}, raw_size_info = '{}' WHERE file_id = {}"

del_folder_files = "UPDATE files SET file_exists = 1 WHERE folder_id = '{}'"

update_md5 = "UPDATE files SET {} = '{}' WHERE file_id = {}"

select_tif_md5 = "SELECT tif_md5, file_name AS md5 FROM files WHERE folder_id = {}"

select_raw_md5 = "SELECT raw_md5, file_name AS md5 FROM files WHERE folder_id = {}"

set_jpg = "UPDATE files SET jpg = {}, jpg_info = '{}' WHERE file_id = {}"

select_file_id = "SELECT file_id FROM files WHERE file_name = '{}' AND folder_id = {}"

check_unique = "SELECT count(*) as dupes FROM files WHERE file_name = '{}' AND folder_id != {} and folder_id in (SELECT folder_id from folders where project_id = {})"

insert_file = "INSERT INTO files (folder_id, file_name, unique_file, file_timestamp) VALUES ({}, '{}', {}, '{}') RETURNING file_id"

select_check_file = "SELECT {} FROM files WHERE file_id = {}"

update_tif_pages = "UPDATE files SET tifpages = {}, tifpages_info = '{}' WHERE file_id = {}"

update_projectchecks = "UPDATE projects SET project_checks = '{}' WHERE project_id = {}"

update_folder_status0 = "UPDATE folders SET status = 0, md5_tif = 1, md5_raw = 1 WHERE folder_id = {}"

update_folder_status9 = "UPDATE folders SET status = 9, error_info = 'Missing {} subfolder' WHERE folder_id = {}"

update_folder_0 = "UPDATE folders SET status = 0 WHERE folder_id = {}"

update_folders_md5 = "UPDATE folders SET md5_{} = 0 WHERE folder_id = {}"

delete_file = "UPDATE files SET file_exists = 1 WHERE file_id = {}"

file_exists = "UPDATE files SET file_exists = 0 WHERE file_id = {}"

get_files = "SELECT f.file_id AS file_id, f.file_name AS file_name, d.path as files_path FROM files f, folders d WHERE f.folder_id = d.folder_id AND d.project_id = {}"

filename_query = "UPDATE files SET valid_name = {} WHERE file_id = {}"
