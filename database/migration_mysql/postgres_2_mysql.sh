psql -U osprey -h localhost osprey -c "\copy (select project_id, project_title, project_alias, project_unit, project_checks, project_postprocessing, project_status, project_description,	project_type, project_method , project_manager, project_url , project_coordurl , project_area , project_start, project_end , project_datastorage , project_img_2_object, case when stats_estimated = 'T' THEN 1 ELSE 0 END as stats_estimated, 	case when images_estimated = 'T' THEN 1 ELSE 0 END as stats_estimated,	case when objects_estimated = 'T' THEN 1 ELSE 0 END as stats_estimated, qc_status, updated_at::timestamp from projects) to 'projects.csv' CSV HEADER;"


mysql -u osprey -h localhost osprey -e "LOAD DATA LOCAL INFILE 'projects.csv' 
INTO TABLE projects
FIELDS TERMINATED BY ',' 
ENCLOSED BY '\"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;"

mysql -u osprey -h localhost osprey < projects.sql
