#Queries for check_folder_md5.py

folder_in_dams = "SELECT delivered_to_dams FROM folders WHERE folder_id = %(folder_id)s"

folder_check_processing = "SELECT processing FROM folders WHERE folder_id = %(folder_id)s"

folder_check_processing_md5 = "SELECT processing_md5 FROM folders WHERE folder_id = %(folder_id)s"

folder_processing_update = "UPDATE folders SET processing_md5 = %(processing)s WHERE folder_id = %(folder_id)s"

select_folderid = "SELECT folder_id FROM folders WHERE project_folder = %(project_folder)s and path = %(folder_path)s and project_id = %(project_id)s"

file_postprocessing1 = "INSERT INTO file_postprocessing (file_id, post_step, post_results) (SELECT file_id, 'md5_matches', 0 FROM files WHERE folder_id =  %(folder_id)s)"

file_postprocessing2 = "INSERT INTO file_postprocessing (file_id, post_step, post_results) (SELECT file_id, 'ready_for_dams', 9 FROM files WHERE folder_id =  %(folder_id)s)"

file_postprocessing3 = "INSERT INTO file_postprocessing (file_id, post_step, post_results) (SELECT file_id, 'in_dams', 9 FROM files WHERE folder_id =  %(folder_id)s)"
