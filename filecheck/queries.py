#Queries for MDfilecheck.py

select_folderid = "SELECT folder_id FROM folders WHERE project_folder = %(project_folder)s and project_id = %(project_id)s"

new_folder = "INSERT INTO folders (project_folder, path, status, project_id) VALUES (%(project_folder)s, %(folder_path)s, 9, %(project_id)s) RETURNING folder_id"

folder_date = "UPDATE folders SET date = %(datequery)s where folder_id = %(folder_id)s"

folder_updated_at = "UPDATE folders SET updated_at = NOW() where folder_id = %(folder_id)s"

file_updated_at = "UPDATE files SET updated_at = NOW() where file_id = %(file_id)s"

file_check = "INSERT INTO file_checks (file_id, file_check, check_results, check_info) VALUES (%(file_id)s, %(file_check)s, %(check_results)s, %(check_info)s) ON CONFLICT (file_id, file_check) DO UPDATE SET check_results = %(check_results)s, check_info = %(check_info)s"

save_md5 = "INSERT INTO file_md5 (file_id, filetype, md5) VALUES (%(file_id)s, %(filetype)s, %(md5)s) ON CONFLICT (file_id, filetype) DO UPDATE SET md5 = %(md5)s"

select_file_md5 = "SELECT md5 FROM file_md5 WHERE file_id = %(file_id)s AND filetype = %(filetype)s"

del_folder_files = "UPDATE files SET file_exists = 1 WHERE folder_id = %(folder_id)s"

update_md5 = "UPDATE files SET md5 = %(md5)s WHERE file_id = %(file_id)s"

select_tif_md5 = "SELECT fd.md5, f.file_name FROM files f, file_md5 fd WHERE f.folder_id = %(folder_id)s AND f.file_id = fd.file_id AND fd.filetype = %(filetype)s"

select_file_id = "SELECT file_id FROM files WHERE file_name = %(file_name)s AND folder_id = %(folder_id)s"

get_filename = "SELECT file_name FROM files WHERE file_id = %(file_id)s"

check_unique = "SELECT file_id FROM files WHERE file_name = %(file_name)s AND folder_id != %(folder_id)s and folder_id in (SELECT folder_id from folders where project_id = %(project_id)s) AND file_id != %(file_id)s"

not_unique = "SELECT project_folder FROM folders WHERE folder_id in (SELECT folder_id FROM files WHERE file_id != %(file_id)s AND file_name = %(file_name)s)"

check_unique_old = "SELECT folder FROM old_names WHERE file_name = %(file_name)s AND project_id = %(project_id)s AND folder NOT IN (SELECT project_folder FROM folders WHERE folder_id = %(folder_id)s)"

insert_file = "INSERT INTO files (folder_id, file_name, file_timestamp) VALUES (%(folder_id)s, %(file_name)s, %(file_timestamp)s) RETURNING file_id"

delete_file = "DELETE FROM files WHERE file_id = %(file_id)s"

select_check_file = "SELECT check_results FROM file_checks WHERE file_id = %(file_id)s and file_check = %(filecheck)s"

update_projectchecks = "UPDATE projects SET project_checks = %(project_file_checks)s WHERE project_id = %(project_id)s"

update_folder_status9 = "UPDATE folders SET status = 9, error_info = %(error_info)s WHERE folder_id = %(folder_id)s"

update_folder_0 = "UPDATE folders SET status = 0 WHERE folder_id = %(folder_id)s"

update_folders_md5 = "INSERT INTO folders_md5 (folder_id, md5_type, md5) VALUES (%(folder_id)s, %(filetype)s, %(md5)s) ON CONFLICT (folder_id, md5_type) DO UPDATE SET md5 = %(md5)s"

update_share = "INSERT INTO projects_shares (project_id, share, localpath, used, updated_at) VALUES (%(project_id)s, %(share)s, %(localpath)s, %(used)s, NOW()) ON CONFLICT (project_id, share) DO UPDATE SET used = %(used)s, localpath = %(localpath)s, updated_at = NOW()"

file_exists = "UPDATE files SET file_exists = %(file_exists)s WHERE file_id = %(file_id)s"

get_files = "SELECT f.file_id AS file_id, f.file_name AS file_name, d.path as files_path FROM files f, folders d WHERE f.folder_id = d.folder_id AND d.project_id = %(project_id)s"

