#!/bin/bash
# 
# 2023-05-10
# 

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select project_id, proj_id, project_title, project_alias, project_unit, project_checks, project_postprocessing, project_status, project_description, project_type, project_method, project_manager, project_section, project_url, project_coordurl, project_area, project_start, CASE WHEN project_end IS NULL THEN NULL ELSE project_end END as project_end, project_datastorage, project_img_2_object, case when stats_estimated = 'T' THEN 1 ELSE 0 END as stats_estimated, case when images_estimated = 'T' THEN 1 ELSE 0 END as stats_estimated, case when objects_estimated = 'T' THEN 1 ELSE 0 END as stats_estimated, qc_status, project_notice, projects_order, skip_project, updated_at::timestamp from projects) to 'projects.csv' CSV HEADER;"

# WHERE (project_id > 123 or project_id = 101)


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select table_id, proj_id, project_id, media_type, media_title, media_link from projects_media WHERE (project_id > 123 or project_id = 101)) to 'projects_media.csv' CSV HEADER;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select folder_id, project_id, project_folder, path as folder_path, status, notes, error_info, date, delivered_to_dams, CASE WHEN processing is True THEN 1 ELSE 0 END as processing, CASE WHEN processing_md5 is True THEN 1 ElSE 0 END as processing_md5, no_files, file_errors from folders WHERE (project_id > 123 or project_id = 101)) to 'folders.csv' CSV HEADER;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select tableID as table_id, folder_id, md5_type, md5, updated_at::timestamp from folders_md5 WHERE folder_id in (SELECT folder_id FROM folders WHERE (project_id > 123 or project_id = 101))) to 'folders_md5.csv' CSV HEADER;"


# folders_links
# No data 

# folders_badges
# No data 

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select tableid, folder_id, badge_type, badge_css, badge_text, updated_at::timestamp from folders_badges) to 'folders_badges.csv' CSV HEADER;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, folder_id, file_name, file_timestamp::timestamp, dams_uan, preview_image, updated_at::timestamp from files WHERE folder_id in (SELECT folder_id FROM folders WHERE (project_id > 123 or project_id = 101))) to 'files.csv' CSV HEADER;"


# WHERE file_id in (select file_id from files WHERE folder_id in (SELECT folder_id FROM folders WHERE (project_id > 123 or project_id = 101)))

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, folder_id, file_check, check_results, check_info, updated_at::timestamp from file_checks WHERE file_id in (select file_id from files WHERE folder_id in (SELECT folder_id FROM folders WHERE (project_id > 123 or project_id = 101)))) to 'files_checks.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, filetype, md5, updated_at::timestamp from file_md5 WHERE file_id in (select file_id from files WHERE folder_id in (SELECT folder_id FROM folders WHERE (project_id > 123 or project_id = 101)))) to 'file_md5.csv' CSV HEADER;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, filetype, filesize, updated_at::timestamp from files_size WHERE file_id in (select file_id from files WHERE folder_id in (SELECT folder_id FROM folders WHERE (project_id > 123 or project_id = 101)))) to 'files_size.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select tableid as table_id, file_id, link_name, link_url, link_notes, updated_at::timestamp from files_links WHERE file_id in (select file_id from files WHERE folder_id in (SELECT folder_id FROM folders WHERE (project_id > 123 or project_id = 101)))) to 'files_links.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 0 and file_id <= 250000) to 'files_exif_1.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 250000 and file_id <= 500000) to 'files_exif_2.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 500000 and file_id <= 620000) to 'files_exif_3_1.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 620000 and file_id <= 750000) to 'files_exif_3_2.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 750000 and file_id <= 1000000) to 'files_exif_4.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1000000 and file_id <= 1250000) to 'files_exif_5.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1250000 and file_id <= 1370000) to 'files_exif_6_1.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1370000 and file_id <= 1400000) to 'files_exif_6_2.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1400000 and file_id <= 1410000) to 'files_exif_6_3.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1410000 and file_id <= 1413500) to 'files_exif_6_3_1.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1413500 and file_id <= 1417000) to 'files_exif_6_3_2.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1417000 and file_id <= 1418500) to 'files_exif_6_3_3.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1418500 and file_id <= 1420000) to 'files_exif_6_3_4.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1420000 and file_id <= 1421000) to 'files_exif_6_4_1_1.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1421000 and file_id <= 1422000) to 'files_exif_6_4_1_2.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1422000 and file_id <= 1423000) to 'files_exif_6_4_1_3.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1423000 and file_id <= 1424000) to 'files_exif_6_4_1_4.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1424000 and file_id <= 1425000) to 'files_exif_6_4_1_5.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1425000 and file_id <= 1430000) to 'files_exif_6_4_2.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1430000 and file_id <= 1435000) to 'files_exif_6_4_3.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1435000 and file_id <= 1440000) to 'files_exif_6_4_4.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1440000 and file_id <= 1500000) to 'files_exif_6_4_5.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1500000 and file_id <= 1750000) to 'files_exif_7.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1750000 and file_id <= 1870000) to 'files_exif_8_1.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1870000 and file_id <= 1910000) to 'files_exif_8_2.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1910000 and file_id <= 1960000) to 'files_exif_8_3.csv' CSV HEADER;"
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 1960000 and file_id <= 2000000) to 'files_exif_8_4.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, tag, value, filetype, tagid, taggroup, updated_at::timestamp from files_exif where file_id not in (select file_id from files where folder_id in (select folder_id from folders where project_id = 100)) and file_id > 2000000) to 'files_exif_9.csv' CSV HEADER;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, post_step, post_results, post_info, updated_at::timestamp from file_postprocessing WHERE file_id in (select file_id from files WHERE folder_id in (SELECT folder_id FROM folders WHERE (project_id > 123 or project_id = 101)))) to 'file_postprocessing.csv' CSV HEADER;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select project_id, collex_total, collex_to_digitize, collex_ready, objects_digitized, images_taken, images_in_dams, images_in_cis, images_public, no_records_in_cis, no_records_in_collexweb, no_records_in_collectionssiedu, no_records_in_gbif, updated_at::timestamp from projects_stats) to 'projects_stats.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select user_id, username, full_name, pass, CASE WHEN user_active is True THEN 1 ElSE 0 END as user_active, CASE WHEN is_admin is True THEN 1 ElSE 0 END as is_admin from qc_users) to 'users.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select id as table_id, project_id, user_id from qc_projects) to 'qc_projects.csv' CSV HEADER;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select project_id, qc_level::text, qc_percent::text, qc_threshold_critical::text, qc_threshold_major::text, qc_threshold_minor::text, qc_normal_percent::text, qc_reduced_percent::text, qc_tightened_percent::text from qc_settings) to 'qc_settings.csv' CSV HEADER;"




psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select folder_id, qc_status, qc_by, qc_ip, qc_info, updated_at::timestamp from qc_folders) to 'qc_folders.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select folder_id, file_id, file_qc, qc_info, qc_by, qc_ip, updated_at::timestamp from qc_files) to 'qc_files.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select report_id, project_id, report_title, report_title_brief, query, query_api, query_updated, updated_at::timestamp from data_reports) to 'data_reports.csv' CSV HEADER;"






psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select * from dams_cdis_file_status_view_dpo) to 'dams_cdis_file_status_view_dpo.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select * from dams_vfcu_file_view_dpo) to 'dams_vfcu_file_view_dpo.csv' CSV HEADER;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select table_id, key, uid, expires_on::timestamp, usage_rate, updated_at::timestamp from api_keys) to 'api_keys.csv' CSV HEADER;"


# psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select table_id, uid, key, expires_on::timestamp, usage_rate, updated_at::timestamp from users) to 'users.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select vfcu_media_file_id, file_name, project_cd, dams_uan, to_dams_ingest_dt::timestamp from dams_cdis_file_status_view_dpo) to 'dams_cdis_file_status_view_dpo.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select vfcu_media_file_id, project_cd, media_file_name, vfcu_pickup_loc, vfcu_checksum from dams_vfcu_file_view_dpo) to 'dams_vfcu_file_view_dpo.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select * from projects_stats_detail where project_id is not null) to 'projects_stats_detail.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select project_id, 'project_checks', unnest(string_to_array(project_checks, ',')) from projects WHERE project_checks is not null) to 'projects_settings_1.csv' CSV HEADER;"

psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select project_id, 'project_postprocessing', unnest(string_to_array(project_postprocessing, ',')) from projects WHERE project_postprocessing is not null) to 'projects_settings_2.csv' CSV HEADER;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select report_id, project_id, report_title, report_title_brief, query, query_api, query_updated, updated_at::timestamp from data_reports) to 'data_reports.csv' CSV HEADER;"




# JPC
psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select table_id, resource_id, refid, archive_box, archive_type, archive_folder, unit_title, url, notes, updated_at::timestamp from jpc_aspace_data) to 'jpc_aspace_data.csv' CSV HEADER;"


psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select table_id, resource_id, repository_id, resource_title, resource_tree, updated_at::timestamp from jpc_aspace_resources) to 'jpc_aspace_resources.csv' CSV HEADER;"

