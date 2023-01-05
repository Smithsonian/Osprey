psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select project_id, project_title, project_alias, project_unit, project_checks, project_postprocessing, project_status, project_description,	project_type, project_method , project_manager, project_url , project_coordurl , project_area , project_start, project_end , project_datastorage , project_img_2_object, case when stats_estimated = 'T' THEN 1 ELSE 0 END as stats_estimated, 	case when images_estimated = 'T' THEN 1 ELSE 0 END as stats_estimated,	case when objects_estimated = 'T' THEN 1 ELSE 0 END as stats_estimated, qc_status, updated_at::timestamp from projects) to 'projects.csv' CSV HEADER;"


mysql -u osprey -h localhost osprey -e "LOAD DATA LOCAL INFILE 'projects.csv' 
INTO TABLE projects
FIELDS TERMINATED BY ',' 
ENCLOSED BY '\"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select table_id, project_id, media_type, media_title, media_link from projects_media) to 'projects_media.csv' CSV HEADER;"



mysql -u osprey -h localhost osprey -e "LOAD DATA LOCAL INFILE 'projects_media.csv' 
INTO TABLE projects_media
FIELDS TERMINATED BY ',' 
ENCLOSED BY '\"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select folder_id, project_id, project_folder, path as folder_path, status, notes, error_info, date, delivered_to_dams, CASE WHEN processing is True THEN 1 ElSE 0 END as processing, CASE WHEN processing_md5 is True THEN 1 ElSE 0 END as processing_md5, no_files, file_errors from folders) to 'folders.csv' CSV HEADER;"



mysql -u osprey -h localhost osprey -e "LOAD DATA LOCAL INFILE 'folders.csv' 
INTO TABLE folders
FIELDS TERMINATED BY ',' 
ENCLOSED BY '\"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;"




psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select tableID, folder_id, md5_type, md5 from folders_md5) to 'folders_md5.csv' CSV HEADER;"



mysql -u osprey -h localhost osprey -e "LOAD DATA LOCAL INFILE 'folders_md5.csv' 
INTO TABLE folders_md5
FIELDS TERMINATED BY ',' 
ENCLOSED BY '\"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;"



psql -U osprey -h si-fsosprey01.si.edu osprey -c "\copy (select file_id, folder_id, file_name, file_timestamp::timestamp, dams_uan, preview_image, created_at::timestamp from files) to 'files.csv' CSV HEADER;"



mysql -u osprey -h localhost osprey -e "LOAD DATA LOCAL INFILE 'files.csv' 
INTO TABLE files
FIELDS TERMINATED BY ',' 
ENCLOSED BY '\"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;"





sudo mysqldump -u root -h localhost osprey > osprey_backup.sql
