SELECT file_id, folder_id, preview_image FROM files WHERE file_name = %(file_name)s AND folder_id IN (SELECT folder_id FROM folders WHERE project_id in(100,131)) LIMIT 1

