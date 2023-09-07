-- MySQL version of the Osprey database 
--  version 2.2.0
--  2023-05-16

-- uuid v4 function
/* CREATE FUNCTION uuid_v4s()
    RETURNS CHAR(36)
BEGIN
    -- 1th and 2nd block are made of 6 random bytes
    SET @h1 = HEX(RANDOM_BYTES(4));
    SET @h2 = HEX(RANDOM_BYTES(2));

    -- 3th block will start with a 4 indicating the version, remaining is random
    SET @h3 = SUBSTR(HEX(RANDOM_BYTES(2)), 2, 3);

    -- 4th block first nibble can only be 8, 9 A or B, remaining is random
    SET @h4 = CONCAT(HEX(FLOOR(ASCII(RANDOM_BYTES(1)) / 64)+8),
                SUBSTR(HEX(RANDOM_BYTES(2)), 2, 3));

    -- 5th block is made of 6 random bytes
    SET @h5 = HEX(RANDOM_BYTES(6));

    -- Build the complete UUID
    RETURN LOWER(CONCAT(
        @h1, '-', @h2, '-4', @h3, '-', @h4, '-', @h5
    ));
end */



-- Drop tables 
DROP TABLE IF EXISTS api_keys CASCADE;
DROP TABLE IF EXISTS qc_files CASCADE;
DROP TABLE IF EXISTS qc_folders CASCADE;
DROP TABLE IF EXISTS qc_settings CASCADE;
DROP TABLE IF EXISTS qc_projects CASCADE;
DROP TABLE IF EXISTS qc_users CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS projects_stats CASCADE;
DROP TABLE IF EXISTS file_postprocessing CASCADE;
DROP TABLE IF EXISTS files_exif CASCADE;
DROP TABLE IF EXISTS files_links CASCADE;
DROP TABLE IF EXISTS files_size CASCADE;
DROP TABLE IF EXISTS file_md5 CASCADE;
DROP TABLE IF EXISTS files_checks CASCADE;
DROP TABLE IF EXISTS files CASCADE;
DROP TABLE IF EXISTS folders_badges CASCADE;
DROP TABLE IF EXISTS folders_links CASCADE;
DROP TABLE IF EXISTS folders_md5 CASCADE;
DROP TABLE IF EXISTS folders CASCADE;
DROP TABLE IF EXISTS projects_links CASCADE;
DROP TABLE IF EXISTS projects CASCADE;
DROP TABLE IF EXISTS dams_cdis_file_status_view_dpo CASCADE;
DROP TABLE IF EXISTS dams_vfcu_file_view_dpo CASCADE;
DROP TABLE IF EXISTS projects_stats_detail CASCADE;



-- users
-- old qc_users
-- DROP TABLE IF EXISTS qc_users CASCADE;
-- DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE users (
    user_id SMALLINT AUTO_INCREMENT PRIMARY KEY,
    username varchar(64),
    full_name varchar(254),
    pass varchar(32),
    user_active boolean DEFAULT 1,
    is_admin boolean DEFAULT 0,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
) DEFAULT CHARSET=utf8mb4;

CREATE INDEX users_uid_idx ON users (user_id) USING BTREE;
CREATE INDEX users_un_idx ON users (username) USING BTREE;
CREATE INDEX users_ua_idx ON users (user_active) USING BTREE;




-- api_keys
-- DROP TABLE IF EXISTS api_keys CASCADE;
CREATE TABLE api_keys (
	table_id MEDIUMINT auto_increment PRIMARY KEY NOT NULL,
	api_key varchar(36) NULL,
	uid varchar(36) NULL REFERENCES users(uid),
	expires_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
	usage_rate SMALLINT DEFAULT 100 NOT NULL,
	updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL
) DEFAULT CHARSET=utf8mb4;


	

-- projects
-- DROP TABLE IF EXISTS projects CASCADE;
CREATE TABLE projects (
    project_id INT AUTO_INCREMENT PRIMARY KEY,
	proj_id VARCHAR(36),
    project_title VARCHAR(254),
    project_alias VARCHAR(64),
    project_unit  VARCHAR(24),
    project_checks VARCHAR(254) DEFAULT 'raw_pair,magick,jhove,tifpages,unique_file',
    project_postprocessing CHAR(254) DEFAULT NULL,
    project_status VARCHAR(24),
    project_description text,
	project_type VARCHAR(24) DEFAULT 'production',
    project_method  VARCHAR(24),
    project_manager VARCHAR(96),
	project_section VARCHAR(4),
    project_coordurl CHAR(254),
    project_area VARCHAR(64),
    project_start DATE,
    project_end DATE,
    project_datastorage VARCHAR(254),
    project_img_2_object VARCHAR(8),
	project_object_query VARCHAR(254),
	dams_project_cd VARCHAR(254),
    stats_estimated boolean DEFAULT 1,
    images_estimated boolean DEFAULT 0,
    objects_estimated boolean DEFAULT 0,
    qc_status TINYINT DEFAULT 0,
	project_notice TEXT,
	projects_order smallint,
	skip_project BOOLEAN DEFAULT 0,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
) DEFAULT CHARSET=utf8mb4;
CREATE INDEX projects_pid_idx ON projects (project_id) USING BTREE;
CREATE INDEX projects_pjd_idx ON projects (proj_id) USING BTREE;
CREATE INDEX projects_palias_idx ON projects (project_alias) USING BTREE;
CREATE INDEX projects_status_idx ON projects (project_status) USING BTREE;




-- projects_settings
-- DROP TABLE IF EXISTS projects_settings
CREATE TABLE projects_settings (
    table_id INT AUTO_INCREMENT PRIMARY KEY,
	project_id INT,
	project_setting VARCHAR(32),
	settings_value VARCHAR(96),
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
) DEFAULT CHARSET=utf8mb4;
CREATE INDEX projects_set_pid_idx ON projects_settings (project_id) USING BTREE;
CREATE INDEX projects_set_pset_idx ON projects_settings (project_setting) USING BTREE;
ALTER TABLE projects_settings ADD CONSTRAINT pid_projset UNIQUE (project_id, project_setting, settings_value);



-- projects_links
-- DROP TABLE IF EXISTS projects_links CASCADE;
CREATE TABLE projects_links (
	table_id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT,
	proj_id BINARY(16),
    link_type varchar(24) DEFAULT 'yt',
    link_title varchar(254),
    url varchar(254) NOT NULL,
    CONSTRAINT fk_projid
    FOREIGN KEY (project_id) 
        REFERENCES projects(project_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
CREATE INDEX projects_links_prid_idx ON projects_links (project_id) USING BTREE;
CREATE INDEX projects_links_pid_idx ON projects_links (proj_id) USING BTREE;




-- folders
-- DROP TABLE IF EXISTS folders CASCADE;
create table folders (
    folder_id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT,
    project_folder VARCHAR(254),
    folder_path VARCHAR(254),
    status INT,
    notes text,
    error_info VARCHAR(254),
    date date,
    delivered_to_dams INT DEFAULT 9,
    processing boolean DEFAULT 0,
    processing_md5 boolean DEFAULT 0,
    no_files INT,
    file_errors INT DEFAULT 9,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fk_foldproj
    FOREIGN KEY (project_id) 
        REFERENCES projects(project_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
CREATE INDEX folders_fid_idx ON folders (folder_id) USING BTREE;
CREATE INDEX folders_pid_idx ON folders (project_id) USING BTREE;




-- folders_md5
-- DROP TABLE IF EXISTS folders_md5 CASCADE;
CREATE TABLE folders_md5 (
    table_id        INT AUTO_INCREMENT PRIMARY KEY,
    folder_id       INT,
    md5_type        VARCHAR(12),
    md5             int,
    updated_at      timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fk_foldmd5
    FOREIGN KEY (folder_id) 
        REFERENCES folders(folder_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
ALTER TABLE folders_md5 ADD UNIQUE `folderid_and_type` (folder_id, md5_type);

CREATE INDEX folders_md5_fid_idx ON folders_md5 (folder_id) USING BTREE;
CREATE INDEX folders_md5_tid_idx ON folders_md5 (table_id) USING BTREE;
ALTER TABLE folders_md5 ADD CONSTRAINT folid_md5 UNIQUE (folder_id, md5_type);


-- folders_links
-- DROP TABLE IF EXISTS folders_links CASCADE;
CREATE TABLE folders_links (
    table_id        INT AUTO_INCREMENT PRIMARY KEY,
    folder_id       INT,
    link_text       VARCHAR(254),
    link_url        VARCHAR(254),
    updated_at      timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fk_foldlink
    FOREIGN KEY (folder_id) 
        REFERENCES folders(folder_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
CREATE INDEX folders_links_tid_idx ON folders_links (table_id) USING BTREE;
CREATE INDEX folders_links_fid_idx ON folders_links (folder_id) USING BTREE;



-- folders_badges
-- DROP TABLE IF EXISTS folders_badges CASCADE;
CREATE TABLE folders_badges (
    table_id        INT AUTO_INCREMENT PRIMARY KEY,
    folder_id       INT,
	badge_type 		VARCHAR(24),
	badge_css		 VARCHAR(24),
    badge_text      VARCHAR(64),
    updated_at      timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fk_foldbadge
    FOREIGN KEY (folder_id) 
        REFERENCES folders(folder_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
ALTER TABLE folders_badges ADD UNIQUE `badge_type_text` (folder_id, badge_type, badge_text);
CREATE INDEX folders_badges_tid_idx ON folders_badges (table_id) USING BTREE;
CREATE INDEX folders_badges_fid_idx ON folders_badges (folder_id) USING BTREE;
CREATE INDEX folders_badges_type_fid_idx ON folders_badges (badge_type) USING BTREE;
ALTER TABLE folders_badges ADD CONSTRAINT fid_type_badge UNIQUE (folder_id, badge_type);


-- files
-- DROP TABLE IF EXISTS files CASCADE;
CREATE TABLE files (
	file_id INT AUTO_INCREMENT PRIMARY KEY,
	uid VARCHAR(36),
	folder_id INT,
	file_name VARCHAR(254),
	file_timestamp     timestamp,
	dams_uan           VARCHAR(254),
	preview_image      VARCHAR(254),
	created_at         timestamp DEFAULT CURRENT_TIMESTAMP,
	updated_at         timestamp DEFAULT CURRENT_TIMESTAMP 
	ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fk_foldfile
	FOREIGN KEY (folder_id) 
	REFERENCES folders(folder_id)
	ON UPDATE CASCADE
	ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;

ALTER TABLE files ADD UNIQUE `files_constr` (file_name, folder_id);
CREATE INDEX files_fileid_idx ON files (file_id) USING BTREE;
CREATE INDEX files_folderid_idx ON files (folder_id) USING BTREE;
CREATE INDEX files_ffid_idx ON files (folder_id, file_id) USING BTREE;
CREATE INDEX files_fileuid_idx ON files (uid) USING BTREE;


-- files_checks
-- DROP TABLE IF EXISTS files_checks CASCADE;
CREATE TABLE files_checks (
	table_id INT AUTO_INCREMENT PRIMARY KEY,
	file_id INT,
	uid VARCHAR(36),
	folder_id INT,
	file_check VARCHAR(64),
	check_results INT,
	check_info TEXT,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP
	ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fckecks_files
	FOREIGN KEY (file_id) 
	REFERENCES files(file_id)
	ON UPDATE CASCADE
	ON DELETE CASCADE,
	CONSTRAINT fckecks_folders
	FOREIGN KEY (folder_id) 
	REFERENCES folders(folder_id)
	ON UPDATE CASCADE
	ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
ALTER TABLE files_checks ADD UNIQUE `filechecks_constr` (file_id, file_check);

CREATE INDEX file_checks1_tid_idx ON files_checks (table_id) USING BTREE;
CREATE INDEX file_checks1_file_id_idx ON files_checks (file_id) USING BTREE;
CREATE INDEX file_checks1_file_uid_idx ON files_checks (uid) USING BTREE;
CREATE INDEX file_checks1_file_check_idx ON files_checks (file_check) USING BTREE;
CREATE INDEX file_checks1_check_results_idx ON files_checks (check_results) USING BTREE;
CREATE INDEX file_checks1_fil_id_idx ON files_checks (file_id, check_results) USING BTREE;
CREATE INDEX file_checks1_fc_id_idx ON files_checks (folder_id, check_results) USING BTREE;
CREATE INDEX file_checks1_ff_id_idx ON files_checks (folder_id, file_id) USING BTREE;
ALTER TABLE files_checks ADD CONSTRAINT fid_check UNIQUE (file_id, file_check);


	
	
	

-- file_md5
-- DROP TABLE IF EXISTS file_md5 CASCADE;
create table file_md5 (
	table_id INT AUTO_INCREMENT PRIMARY KEY,
    file_id INT,
    filetype VARCHAR(8),
    md5 VARCHAR(128),
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fmd5_files
    FOREIGN KEY (file_id) 
        REFERENCES files(file_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
ALTER TABLE file_md5 ADD UNIQUE `file_and_type` (file_id, filetype);

CREATE INDEX file_md5_tid_idx ON file_md5 (table_id) USING BTREE;
CREATE INDEX file_md5_file_id_idx ON file_md5 (file_id) USING BTREE;
CREATE INDEX file_md5_filetype_idx ON file_md5 (filetype) USING BTREE;
CREATE INDEX file_md5_file_id2_idx ON file_md5 (file_id, filetype) USING BTREE;

	
	

-- files_size
-- DROP TABLE IF EXISTS files_size CASCADE;
create table files_size (
	table_id INT AUTO_INCREMENT PRIMARY KEY,
    file_id INT,
    filetype varchar(8) DEFAULT 'TIF',
    filesize varchar(64),
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fsize_files
    FOREIGN KEY (file_id) 
        REFERENCES files(file_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
ALTER TABLE files_size ADD CONSTRAINT filesize_fileid_filetype UNIQUE (file_id, filetype);

CREATE INDEX files_size_tid_idx ON files_size (table_id) USING BTREE;
CREATE INDEX files_size_file_id_idx ON files_size (file_id) USING BTREE;
CREATE INDEX files_size_filetype_idx ON files_size (filetype) USING BTREE;
CREATE INDEX files_size_file_id2_idx ON files_size (file_id, filetype) USING BTREE;
ALTER TABLE files_size ADD CONSTRAINT fid_ftype UNIQUE (file_id, filetype);


	

-- files_links
-- DROP TABLE IF EXISTS files_links CASCADE;
CREATE TABLE files_links (
    table_id        serial,
    file_id 		INT,
    link_name       VARCHAR(254),
    link_url        VARCHAR(254),
    link_notes      VARCHAR(254),
    updated_at      timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT flinks_files
    FOREIGN KEY (file_id) 
        REFERENCES files(file_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
CREATE INDEX files_links_tid_idx ON files_links (table_id) USING BTREE;
CREATE INDEX files_links_fid_idx ON files_links (file_id) USING BTREE;
CREATE INDEX files_links_lnk_idx ON files_links (link_name) USING BTREE;



-- files_exif
-- DROP TABLE IF EXISTS files_exif CASCADE;
create table files_exif (
    table_id serial,
	file_id integer,
    filetype varchar(8) default 'TIF',
    tag varchar(254),
    taggroup varchar(254),
    tagid varchar(128),
    value text,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fexif_files
    FOREIGN KEY (file_id) 
        REFERENCES files(file_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
ALTER TABLE files_exif ADD CONSTRAINT fid_type_tag UNIQUE (file_id, filetype, tagid, tag, taggroup);
CREATE INDEX files_exif1_tid_idx ON files_exif (table_id) USING BTREE;
CREATE INDEX files_exif1_file_id_idx ON files_exif (file_id) USING BTREE;
CREATE INDEX files_exif1_filetype_idx ON files_exif (filetype) USING BTREE;
CREATE INDEX files_exif1_fid_idx ON files_exif (file_id, filetype) USING BTREE;
CREATE INDEX files_exif1_tag_idx ON files_exif (tag) USING BTREE;
CREATE INDEX files_exif1_tagid_idx ON files_exif (tagid) USING BTREE;
CREATE INDEX files_exif1_taggroup_idx ON files_exif (taggroup) USING BTREE;



-- files_exif_old
-- DROP TABLE IF EXISTS files_exif_old CASCADE;
create table files_exif_old (
    table_id serial,
	file_id integer,
    filetype varchar(8) default 'TIF',
    tag varchar(254),
    taggroup varchar(254),
    tagid varchar(128),
    value text,
	updated_at timestamp,
	CONSTRAINT fexif_files_o
    FOREIGN KEY (file_id) 
        REFERENCES files(file_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
ALTER TABLE files_exif_old ADD CONSTRAINT fid_type_tago UNIQUE (file_id, filetype, tagid, tag, taggroup);
CREATE INDEX files_exifo_tid_idx ON files_exif_old (table_id) USING BTREE;
CREATE INDEX files_exifo_file_id_idx ON files_exif_old (file_id) USING BTREE;
CREATE INDEX files_exifo_filetype_idx ON files_exif_old (filetype) USING BTREE;
CREATE INDEX files_exifo_fid_idx ON files_exif_old (file_id, filetype) USING BTREE;
CREATE INDEX files_exifo_tag_idx ON files_exif_old (tag) USING BTREE;
CREATE INDEX files_exifo_tagid_idx ON files_exif_old (tagid) USING BTREE;
CREATE INDEX files_exifo_taggroup_idx ON files_exif_old (taggroup) USING BTREE;




-- file_postprocessing
-- DROP TABLE IF EXISTS file_postprocessing CASCADE;
CREATE TABLE file_postprocessing (
	table_id serial PRIMARY KEY,
    file_id INT,
    post_step VARCHAR(64),
    post_results integer,
    post_info text,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fpost_files
    FOREIGN KEY (file_id) 
        REFERENCES files(file_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
ALTER TABLE file_postprocessing ADD CONSTRAINT fpp_fileid_and_poststep UNIQUE (file_id, post_step);

CREATE INDEX file_postprocessing_tid_idx ON file_postprocessing (table_id) USING BTREE;
CREATE INDEX file_postprocessing_file_id_idx ON file_postprocessing (file_id) USING BTREE;
CREATE INDEX file_postprocessing_post_step_idx ON file_postprocessing (post_step) USING BTREE;
CREATE INDEX file_postprocessing_check_results_idx ON file_postprocessing (post_results) USING BTREE;

ALTER TABLE file_postprocessing ADD CONSTRAINT fid_postst UNIQUE (file_id, post_step);



-- projects_stats
-- DROP TABLE IF EXISTS projects_stats CASCADE;
CREATE TABLE projects_stats (
    project_id INT,
    collex_total integer,
    collex_to_digitize integer,
    collex_ready integer,
    objects_digitized integer,
    images_taken integer,
    images_in_dams integer,
    images_in_cis integer,
    images_public integer,
    no_records_in_cis integer,
    no_records_in_collexweb integer,
    no_records_in_collectionssiedu integer,
    no_records_in_gbif integer,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT pstats_proj
    FOREIGN KEY (project_id) 
        REFERENCES projects(project_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;

CREATE INDEX projects_stats_pid_idx on projects_stats (project_id) USING BTREE;



/* 
-- qc_users
-- DROP TABLE IF EXISTS qc_users CASCADE;
CREATE TABLE qc_users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username varchar(64),
    full_name varchar(254),
    pass varchar(254),
    user_active boolean DEFAULT 1,
    is_admin boolean DEFAULT 0,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
) DEFAULT CHARSET=utf8mb4;

CREATE INDEX qc_users_uid_idx ON qc_users (user_id) USING BTREE;
CREATE INDEX qc_users_un_idx ON qc_users (username) USING BTREE;
CREATE INDEX qc_users_ua_idx ON qc_users (user_active) USING BTREE;

LOAD DATA LOCAL INFILE 'qc_users.csv' 
	INTO TABLE qc_users 
	FIELDS TERMINATED BY ',' 
	ENCLOSED BY '\"'
	LINES TERMINATED BY '\n'
	IGNORE 1 ROWS
	(user_id, username, full_name, pass, user_active, is_admin); */




-- projects assigned to users
-- DROP TABLE IF EXISTS qc_projects CASCADE;
create table qc_projects (
    table_id serial PRIMARY KEY,
    project_id INT,
    user_id SMALLINT,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT qcp_proj
    FOREIGN KEY (project_id) 
        REFERENCES projects(project_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;
ALTER TABLE qc_projects 
	ADD CONSTRAINT qcp_uid1
	FOREIGN KEY (user_id)
	REFERENCES users(user_id)
	ON UPDATE CASCADE
	ON DELETE CASCADE;
CREATE INDEX qc_projects_fid_idx ON qc_projects (project_id) USING BTREE;
CREATE INDEX qc_projects_pid_idx ON qc_projects (user_id) USING BTREE;





-- qc_settings
-- DROP TABLE IF EXISTS qc_settings CASCADE;
create table qc_settings (
    project_id INT,
    qc_level VARCHAR(24) DEFAULT 'Normal',
    qc_percent VARCHAR(8) DEFAULT '10',
    qc_threshold_critical VARCHAR(8) DEFAULT '0',
    qc_threshold_major VARCHAR(8) DEFAULT '0.015',
    qc_threshold_minor VARCHAR(8) DEFAULT '0.04',
    qc_normal_percent VARCHAR(8) DEFAULT '10',
    qc_reduced_percent VARCHAR(8) DEFAULT '5',
    qc_tightened_percent VARCHAR(8) DEFAULT '40',
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT qset_proj
    FOREIGN KEY (project_id) 
        REFERENCES projects(project_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;

CREATE INDEX qc_settings_pid_idx ON qc_settings (project_id) USING BTREE;





-- qc_folders
-- DROP TABLE IF EXISTS qc_folders CASCADE;
create table qc_folders (
	table_id serial primary key,
    folder_id INT,
    qc_status INT DEFAULT 9,
    qc_by INT,
    qc_ip VARCHAR(64),
    qc_info VARCHAR(254),
	qc_level VARCHAR(64),
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT qfol_fol
    FOREIGN KEY (folder_id) 
        REFERENCES folders(folder_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;

CREATE INDEX qc_folders_fid_idx ON qc_folders (folder_id) USING BTREE;
CREATE INDEX qc_folders_qby_idx ON qc_folders (qc_by) USING BTREE;
CREATE INDEX qc_folders_qstat_idx ON qc_folders (qc_status) USING BTREE;
CREATE INDEX qc_folders_qlevel_idx ON qc_folders (qc_level) USING BTREE;



-- qc_files
-- DROP TABLE IF EXISTS qc_files CASCADE;
create table qc_files (
	table_id serial primary key,
    folder_id INT,
    file_id INT,
    file_qc INT DEFAULT 9,
    qc_info VARCHAR(254),
    qc_by INT,
    qc_ip VARCHAR(64),
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT qc_fold
    FOREIGN KEY (folder_id) 
        REFERENCES folders(folder_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE,
	CONSTRAINT qc_files
    FOREIGN KEY (file_id) 
        REFERENCES files(file_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;

CREATE INDEX qc_files_fid_idx ON qc_files (file_id) USING BTREE;
CREATE INDEX qc_files_fold_idx ON qc_files (folder_id) USING BTREE;




-- dams_cdis_file_status_view_dpo
CREATE TABLE dams_cdis_file_status_view_dpo (
	vfcu_media_file_id varchar(12),
	file_name varchar(254),
	project_cd varchar(96),
	dams_uan varchar(96) DEFAULT NULL,
	to_dams_ingest_dt timestamp
);
CREATE INDEX dams_cdis_stat_damsuan_idx ON dams_cdis_file_status_view_dpo (dams_uan) USING btree;
CREATE INDEX dams_cdis_stat_fileid_idx ON dams_cdis_file_status_view_dpo (vfcu_media_file_id) USING btree;
CREATE INDEX dams_cdis_stat_filename_idx ON dams_cdis_file_status_view_dpo (file_name) USING btree;
CREATE INDEX dams_cdis_stat_pcd_idx ON dams_cdis_file_status_view_dpo (project_cd) USING btree;





CREATE TABLE dams_vfcu_file_view_dpo (
	vfcu_media_file_id varchar(12),
	project_cd varchar(96),
	media_file_name varchar(254),
	vfcu_pickup_loc varchar(254),
	vfcu_checksum varchar(32)
);
CREATE INDEX dams_vfcu_file_fileid_idx ON dams_vfcu_file_view_dpo (vfcu_media_file_id) USING btree;
CREATE INDEX dams_vfcu_file_mediafilename_idx ON dams_vfcu_file_view_dpo (media_file_name) USING btree;
CREATE INDEX dams_vfcu_file_pickuploc_idx ON dams_vfcu_file_view_dpo (vfcu_pickup_loc) USING btree;
CREATE INDEX dams_vfcu_file_projectid_idx ON dams_vfcu_file_view_dpo (project_cd) USING btree;


-- DROP TABLE IF EXISTS projects_stats_detail CASCADE;
CREATE TABLE projects_stats_detail (
	project_id int NULL,
	time_interval varchar(96) NULL,
	stat_date date NULL,
	objects_digitized int NULL,
	images_captured int NULL,
	project_cd text NULL
);
CREATE INDEX projects_stats_detail_pid_idx ON projects_stats_detail (project_id) USING btree;
CREATE INDEX projects_stats_detail_ti_idx ON projects_stats_detail (time_interval) USING btree;




-- data_reports
-- DROP TABLE IF EXISTS data_reports CASCADE;
CREATE TABLE data_reports (
	report_id varchar(64) NOT NULL PRIMARY KEY,
	report_alias varchar(64),
	project_id int NOT NULL,
	report_title varchar(264) NOT NULL,
	report_title_brief varchar(64) NULL,
	query TEXT NOT NULL,
	query_api TEXT NOT NULL,
	query_updated TEXT NOT NULL,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT project_id
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
		ON UPDATE CASCADE
        ON DELETE CASCADE
);
CREATE INDEX data_reports_pid_idx ON data_reports (project_id) USING btree;
CREATE INDEX data_reports_rid_idx ON data_reports (report_id) USING btree;
CREATE INDEX data_reports_ralias_idx ON data_reports (report_alias) USING btree;



-- si_units
-- DROP TABLE IF EXISTS si_units;
CREATE TABLE si_units (
	unit_id varchar(12) NOT NULL PRIMARY KEY,
	unit_fullname varchar(128) NOT NULL
);
CREATE INDEX si_units_id_idx ON si_units (unit_id) USING btree;




-- DROP TABLE IF EXISTS jpc_aspace_data CASCADE;
CREATE TABLE jpc_aspace_data (
	table_id varchar(64) NOT NULL,
	resource_id varchar(128) NOT NULL,
	refid varchar(64) NOT NULL,
	archive_box varchar(64) NOT NULL,
	archive_type varchar(64) NULL,
	archive_folder varchar(64) NOT NULL,
	unit_title varchar(168) NULL,
	url varchar(254) NULL,
	notes text NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE INDEX jpc_aspace_data_box_idx ON jpc_aspace_data (archive_box) USING btree;
CREATE INDEX jpc_aspace_data_folder_idx ON jpc_aspace_data (archive_folder) USING btree;
CREATE INDEX jpc_aspace_data_name_idx ON jpc_aspace_data (unit_title) USING btree;
CREATE INDEX jpc_aspace_data_refid_idx ON jpc_aspace_data (refid) USING btree;
CREATE INDEX jpc_aspace_data_resid_idx ON jpc_aspace_data (resource_id) USING btree;
CREATE INDEX jpc_aspace_data_type_idx ON jpc_aspace_data (archive_type) USING btree;


-- DROP TABLE IF EXISTS jpc_aspace_resources CASCADE;
CREATE TABLE jpc_aspace_resources (
	table_id varchar(64) NOT NULL,
	resource_id varchar(128) NOT NULL,
	repository_id varchar(128) NOT NULL,
	resource_title varchar(128) NOT NULL,
	resource_tree varchar(128) NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE INDEX jpc_aspace_resources_resid_idx ON jpc_aspace_resources (resource_id) USING btree;
CREATE INDEX jpc_aspace_resources_tid_idx ON jpc_aspace_resources (table_id) USING btree;


-- DROP TABLE IF EXISTS jpc_massdigi_ids CASCADE;
CREATE TABLE jpc_massdigi_ids (
	table_id SERIAL PRIMARY KEY,
	id_relationship varchar(128) NOT NULL,
	id1_value varchar(128) NOT NULL,
	id2_value varchar(128) NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE INDEX jpc_massdigi_tabid_idx ON jpc_massdigi_ids (table_id) USING btree;
CREATE INDEX jpc_massdigi_idrel_val_idx ON jpc_massdigi_ids (id_relationship) USING btree;
CREATE INDEX jpc_massdigi_id1_val_idx ON jpc_massdigi_ids (id1_value) USING btree;
CREATE INDEX jpc_massdigi_id2_val_idx ON jpc_massdigi_ids (id2_value) USING btree;
