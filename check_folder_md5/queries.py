#Queries for check_folder_md5.py

folder_in_dams = "SELECT delivered_to_dams FROM folders WHERE folder_id = %(folder_id)s"

folder_check_processing = "SELECT processing FROM folders WHERE folder_id = %(folder_id)s"

folder_processing_update = "UPDATE folders SET processing_md5 = %(processing)s WHERE folder_id = %(folder_id)s"

select_folderid = "SELECT folder_id FROM folders WHERE project_folder = %(project_folder)s and path = %(folder_path)s and project_id = %(project_id)s"

