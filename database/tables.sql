
-- UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

--Postgres function to update the column last_update on files when the row is updated
CREATE FUNCTION updated_at_files() RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$;



--main projects table
DROP TABLE IF EXISTS projects CASCADE;
DROP SEQUENCE IF EXISTS projects_project_id_seq;
CREATE SEQUENCE projects_project_id_seq MINVALUE 100;
CREATE TABLE projects (
    project_id integer NOT NULL DEFAULT nextval('projects_project_id_seq') PRIMARY KEY,
	proj_id uuid NOT NULL DEFAULT uuid_generate_v4(),
    project_title text,
    project_alias text,
    project_unit  text,
    project_checks text DEFAULT 'raw_pair,magick,jhove,tifpages,unique_file',
    project_postprocessing text DEFAULT NULL,
    project_acronym text,
    project_status text,
    project_description text,
    project_keywords text,
    project_method  text,
    project_manager text,
    project_url text,
    project_coordurl text,
    project_share text,
    project_area text,
    project_start date,
    project_end date,
    project_datastorage text,
    project_img_2_object numeric DEFAULT 1.0,
    dpoir boolean DEFAULT 't',
    stats_estimated bool DEFAULT 't',
    images_estimated bool DEFAULT 'f',
    objects_estimated bool DEFAULT 'f',
    filecheck_link text,
    process_summary text DEFAULT null,
    qc_status integer DEFAULT 0,
	project_notice text,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX projects_pid_idx ON projects USING BTREE(project_id);
CREATE INDEX projects_pjid_idx ON projects USING BTREE(proj_id);
CREATE INDEX projects_palias_idx ON projects USING BTREE(project_alias);
CREATE INDEX projects_status_idx ON projects USING BTREE(project_status);
CREATE INDEX projects_dpoir_idx ON projects USING BTREE(dpoir);

ALTER TABLE projects ADD COLUMN project_type text DEFAULT 'production';


--Videos and news links
DROP TABLE IF EXISTS projects_media CASCADE;
CREATE TABLE projects_media (
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
	proj_id uuid NOT NULL DEFAULT uuid_generate_v4(),
    media_type text DEFAULT 'yt',
    media_title text,
    media_link text NOT NULL
);
CREATE INDEX projects_media_pid_idx ON projects_media USING BTREE(project_id);
CREATE INDEX projects_media_pjd_idx ON projects_media USING BTREE(proj_id);

UPDATE projects_media m SET proj_id = p.proj_id FROM projects p WHERE m.project_id=p.project_id;


--Budget by project
DROP TABLE IF EXISTS projects_budget CASCADE;
CREATE TABLE projects_budget (
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    budget_type text DEFAULT 'production',
    budget_source text,
    budget_amount numeric
);
CREATE INDEX projects_budget_pid_idx ON projects_budget USING BTREE(project_id);


--items in edan for each project, if available
DROP TABLE IF EXISTS projects_edan CASCADE;
CREATE TABLE projects_edan (
    pe_id serial PRIMARY KEY,
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    edan_id text,
    dams_only bool DEFAULT 'f',
    title text,
    link text,
    credit text,
    notes text,
    idsid text,
    img_file text,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX projects_edan_pid_idx ON projects_edan USING BTREE(project_id);


--Alerts for the dashboard
DROP TABLE IF EXISTS projects_alerts CASCADE;
CREATE TABLE projects_alerts (
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    project_message text,
    active boolean DEFAULT 't',
    updated_at timestamp with time zone
);
CREATE INDEX projects_alerts_pid_idx ON projects_alerts USING BTREE(project_id);



--Shares for the project
--projects_shares
DROP TABLE IF EXISTS projects_shares CASCADE;
CREATE TABLE projects_shares (
    project_id      integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    share           text,
    localpath       text,
    used            text,
    total           text,
    updated_at      timestamp with time zone DEFAULT NOW()
);
ALTER TABLE projects_shares ADD CONSTRAINT projects_shares_proj_and_share UNIQUE (project_id, share);
CREATE INDEX projects_shares_pid_idx ON projects_shares USING BTREE(project_id);



--folders for a project
DROP TABLE IF EXISTS folders CASCADE;
DROP SEQUENCE IF EXISTS folders_folder_id_seq;
CREATE SEQUENCE folders_folder_id_seq MINVALUE 100;
create table folders (
    folder_id integer NOT NULL DEFAULT nextval('folders_folder_id_seq') PRIMARY KEY,
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    project_folder text,
    path text,
    status integer,
    notes text,
    error_info text,
    date date,
    delivered_to_dams integer default 9,
    processing boolean DEFAULT 'f',
    processing_md5 boolean DEFAULT 'f',
    no_files integer,
    file_errors integer DEFAULT 9,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX folders_fid_idx ON folders USING BTREE(folder_id);
CREATE INDEX folders_pid_idx ON folders USING BTREE(project_id);


--folders_md5
DROP TABLE IF EXISTS folders_md5 CASCADE;
CREATE TABLE folders_md5 (
    tableID         serial,
    folder_id       integer REFERENCES folders(folder_id) ON DELETE CASCADE ON UPDATE CASCADE,
    md5_type        text,
    md5             int,
    updated_at      timestamp with time zone DEFAULT NOW()
);
ALTER TABLE folders_md5 ADD CONSTRAINT folderid_and_type UNIQUE (folder_id, md5_type);
CREATE INDEX folders_md5_fid_idx ON folders_md5 USING BTREE(folder_id);


--folders_links
DROP TABLE IF EXISTS folders_links CASCADE;
CREATE TABLE folders_links (
    tableID         serial,
    folder_id       integer REFERENCES folders(folder_id) ON DELETE CASCADE ON UPDATE CASCADE,
    link_text       text,
    link_url        text,
    updated_at      timestamp with time zone DEFAULT NOW()
);
CREATE INDEX folders_links_fid_idx ON folders_links USING BTREE(folder_id);



--folders_badges
DROP TABLE IF EXISTS folders_badges CASCADE;
CREATE TABLE folders_badges (
    tableID         serial,
    folder_id       integer REFERENCES folders(folder_id) ON DELETE CASCADE ON UPDATE CASCADE,
	badge_type 		text,
	badge_css		text,
    badge_text      text,
    updated_at      timestamp with time zone DEFAULT NOW()
);
ALTER TABLE folders_badges ADD CONSTRAINT badge_type_text UNIQUE (folder_id, badge_type, badge_text);
CREATE INDEX folders_badges_fid_idx ON folders_badges USING BTREE(folder_id);
CREATE INDEX folders_badges_type_fid_idx ON folders_badges USING BTREE(badge_type);



--files main table
DROP TABLE IF EXISTS files CASCADE;
DROP SEQUENCE IF EXISTS files_fileid_seq;
CREATE SEQUENCE files_fileid_seq MINVALUE 100;
CREATE TABLE files (
    file_id integer NOT NULL DEFAULT nextval('files_fileid_seq') PRIMARY KEY,
    folder_id integer REFERENCES folders(folder_id) ON DELETE CASCADE ON UPDATE CASCADE,
    file_name text,
    accession_no       text,
    barcode            text,
    file_exists        integer,
    file_timestamp     timestamp with time zone,
    item_no            text,
    dams_uan           text,
    edan_id            text,
    preview_image      text,
    created_at         timestamp with time zone DEFAULT NOW(),
    updated_at         timestamp with time zone DEFAULT NOW()
);
ALTER TABLE files ADD CONSTRAINT files_constr UNIQUE (file_name, folder_id);
CREATE INDEX files_fileid_idx ON files USING BTREE(file_id);
CREATE INDEX files_folderid_idx ON files USING BTREE(folder_id);
CREATE INDEX files_ffid_idx ON files USING BTREE(folder_id, file_id);
CREATE INDEX files_uan_idx ON files USING BTREE(dams_uan);
CREATE INDEX files_eid_idx ON files USING BTREE(edan_id);


CREATE TRIGGER trigger_updated_at_files
  BEFORE UPDATE ON files
  FOR EACH ROW
  EXECUTE PROCEDURE updated_at_files();



  --files_to_dams
  DROP TABLE IF EXISTS files_to_dams CASCADE;
  CREATE TABLE files_to_dams (
      tableID         serial,
      file_id integer REFERENCES files(file_id) ON DELETE CASCADE ON UPDATE CASCADE,
      step_order      integer,
      step            text,
      notes           text,
      updated_at      timestamp with time zone DEFAULT NOW()
  );
  ALTER TABLE files_to_dams ADD CONSTRAINT fileid_and_step UNIQUE (file_id, step);
  CREATE INDEX files_to_dams_fid_idx ON files_to_dams USING BTREE(file_id);



--files_links
DROP TABLE IF EXISTS files_links CASCADE;
CREATE TABLE files_links (
    tableID         serial,
    file_id integer REFERENCES files(file_id) ON DELETE CASCADE ON UPDATE CASCADE,
    link_name       text,
    link_url        text,
    link_notes      text,
    updated_at      timestamp with time zone DEFAULT NOW()
);
CREATE INDEX files_links_fid_idx ON files_links USING BTREE(file_id);
CREATE INDEX files_links_lnk_idx ON files_links USING BTREE(link_name);



--file_md5
DROP TABLE IF EXISTS file_md5 CASCADE;
create table file_md5 (
    file_id integer REFERENCES files(file_id) ON DELETE CASCADE ON UPDATE CASCADE,
    filetype text,
    md5 text,
    updated_at timestamp with time zone DEFAULT NOW()
);
ALTER TABLE file_md5 ADD CONSTRAINT file_and_type UNIQUE (file_id, filetype);
CREATE INDEX file_md5_file_id_idx ON file_md5 USING BTREE(file_id);
CREATE INDEX file_md5_filetype_idx ON file_md5 USING BTREE(filetype);



--files_exif
DROP TABLE IF EXISTS files_exif CASCADE;
create table files_exif (
    file_id integer,
    filetype text default 'TIF',
    tag text,
    taggroup text,
    tagid text,
    value text,
    UNIQUE (file_id, tag, filetype),
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX files_exif1_file_id_idx ON files_exif USING BTREE(file_id);
CREATE INDEX files_exif1_filetype_idx ON files_exif USING BTREE(filetype);
CREATE INDEX files_exif1_fid_idx ON files_exif USING BTREE(file_id, filetype);
CREATE INDEX files_exif1_tag_idx ON files_exif USING BTREE(tag);
CREATE INDEX files_exif1_tagid_idx ON files_exif USING BTREE(tagid);
CREATE INDEX files_exif1_taggroup_idx ON files_exif USING BTREE(taggroup);

--
--     --files_exif partitioned by id
--     CREATE TABLE files_exif_00 (
--         CHECK (file_id < 200000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_01 (
--         CHECK (file_id >= 200000::int AND file_id < 400000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_02 (
--         CHECK (file_id >= 400000::int AND file_id < 600000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_03 (
--         CHECK (file_id >= 600000::int AND file_id < 800000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_04 (
--         CHECK (file_id >= 800000::int AND file_id < 1000000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_05 (
--         CHECK (file_id >= 1000000::int AND file_id < 1200000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_06 (
--         CHECK (file_id >= 1200000::int AND file_id < 1400000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_07 (
--         CHECK (file_id >= 1400000::int AND file_id < 1600000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_08 (
--         CHECK (file_id >= 1600000::int AND file_id < 1800000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_09 (
--         CHECK (file_id >= 1800000::int AND file_id < 2000000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_10 (
--         CHECK (file_id >= 2000000::int AND file_id < 2200000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_11 (
--         CHECK (file_id >= 2200000::int AND file_id < 2400000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_12 (
--         CHECK (file_id >= 2400000::int AND file_id < 2600000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_13 (
--         CHECK (file_id >= 2600000::int AND file_id < 2800000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_14 (
--         CHECK (file_id >= 2800000::int AND file_id < 3000000::int)
--     ) INHERITS (files_exif);
--
--     CREATE TABLE files_exif_15 (
--         CHECK (file_id >= 3000000::int)
--     ) INHERITS (files_exif);
--
--     ALTER TABLE files_exif_00 ADD CONSTRAINT files_exif_00_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_01 ADD CONSTRAINT files_exif_01_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_02 ADD CONSTRAINT files_exif_02_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_03 ADD CONSTRAINT files_exif_03_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_04 ADD CONSTRAINT files_exif_04_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_05 ADD CONSTRAINT files_exif_05_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_06 ADD CONSTRAINT files_exif_06_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_07 ADD CONSTRAINT files_exif_07_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_08 ADD CONSTRAINT files_exif_08_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_09 ADD CONSTRAINT files_exif_09_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_10 ADD CONSTRAINT files_exif_10_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_11 ADD CONSTRAINT files_exif_11_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_12 ADD CONSTRAINT files_exif_12_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_13 ADD CONSTRAINT files_exif_13_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_14 ADD CONSTRAINT files_exif_14_fexif UNIQUE (file_id, tag, filetype);
--     ALTER TABLE files_exif_15 ADD CONSTRAINT files_exif_15_fexif UNIQUE (file_id, tag, filetype);
--
--
--     ----------------------
--     --Function to insert into the specific subtable
--     ----------------------
--
--     CREATE OR REPLACE FUNCTION exif_insert_data() RETURNS TRIGGER AS $$
--     BEGIN
--         IF ( NEW.file_id < 200000::int ) THEN INSERT INTO files_exif_00 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 200000::int AND NEW.file_id < 400000::int ) THEN INSERT INTO files_exif_01 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 400000::int AND NEW.file_id < 600000::int ) THEN INSERT INTO files_exif_02 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 600000::int AND NEW.file_id < 800000::int ) THEN INSERT INTO files_exif_03 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 800000::int AND NEW.file_id < 1000000::int ) THEN INSERT INTO files_exif_04 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 1000000::int AND NEW.file_id < 1200000::int ) THEN INSERT INTO files_exif_05 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 1200000::int AND NEW.file_id < 1400000::int ) THEN INSERT INTO files_exif_06 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 1400000::int AND NEW.file_id < 1600000::int ) THEN INSERT INTO files_exif_07 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 1600000::int AND NEW.file_id < 1800000::int ) THEN INSERT INTO files_exif_08 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 1800000::int AND NEW.file_id < 2000000::int ) THEN INSERT INTO files_exif_09 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 2000000::int AND NEW.file_id < 2200000::int ) THEN INSERT INTO files_exif_10 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 2200000::int AND NEW.file_id < 2400000::int ) THEN INSERT INTO files_exif_11 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 2400000::int AND NEW.file_id < 2600000::int ) THEN INSERT INTO files_exif_12 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 2600000::int AND NEW.file_id < 2800000::int ) THEN INSERT INTO files_exif_13 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 2800000::int AND NEW.file_id < 3000000::int ) THEN INSERT INTO files_exif_14 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--           ELSIF
--           ( NEW.file_id >= 3000000::int ) THEN INSERT INTO files_exif_15 VALUES (NEW.*) ON CONFLICT (file_id, filetype, tag) DO UPDATE SET NEW.value = value;
--
--         END IF;
--         RETURN NULL;
--     END;
--     $$ LANGUAGE plpgsql;
--
--
--     ----------------------
--     --Trigger for insert
--     ----------------------
--     CREATE TRIGGER exif_insert_trigger
--     BEFORE INSERT ON files_exif
--     FOR EACH ROW EXECUTE PROCEDURE exif_insert_data();
--
--
--     CREATE INDEX files_exif_00_file_id_idx ON files_exif_00 USING BTREE(file_id);
--     CREATE INDEX files_exif_00_filetype_idx ON files_exif_00 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_01_file_id_idx ON files_exif_01 USING BTREE(file_id);
--     CREATE INDEX files_exif_01_filetype_idx ON files_exif_01 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_02_file_id_idx ON files_exif_02 USING BTREE(file_id);
--     CREATE INDEX files_exif_02_filetype_idx ON files_exif_02 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_03_file_id_idx ON files_exif_03 USING BTREE(file_id);
--     CREATE INDEX files_exif_03_filetype_idx ON files_exif_03 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_04_file_id_idx ON files_exif_04 USING BTREE(file_id);
--     CREATE INDEX files_exif_04_filetype_idx ON files_exif_04 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_05_file_id_idx ON files_exif_05 USING BTREE(file_id);
--     CREATE INDEX files_exif_05_filetype_idx ON files_exif_05 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_06_file_id_idx ON files_exif_06 USING BTREE(file_id);
--     CREATE INDEX files_exif_06_filetype_idx ON files_exif_06 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_07_file_id_idx ON files_exif_07 USING BTREE(file_id);
--     CREATE INDEX files_exif_07_filetype_idx ON files_exif_07 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_08_file_id_idx ON files_exif_08 USING BTREE(file_id);
--     CREATE INDEX files_exif_08_filetype_idx ON files_exif_08 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_09_file_id_idx ON files_exif_09 USING BTREE(file_id);
--     CREATE INDEX files_exif_09_filetype_idx ON files_exif_09 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_10_file_id_idx ON files_exif_10 USING BTREE(file_id);
--     CREATE INDEX files_exif_10_filetype_idx ON files_exif_10 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_11_file_id_idx ON files_exif_11 USING BTREE(file_id);
--     CREATE INDEX files_exif_11_filetype_idx ON files_exif_11 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_12_file_id_idx ON files_exif_12 USING BTREE(file_id);
--     CREATE INDEX files_exif_12_filetype_idx ON files_exif_12 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_13_file_id_idx ON files_exif_13 USING BTREE(file_id);
--     CREATE INDEX files_exif_13_filetype_idx ON files_exif_13 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_14_file_id_idx ON files_exif_14 USING BTREE(file_id);
--     CREATE INDEX files_exif_14_filetype_idx ON files_exif_14 USING BTREE(filetype);
--
--     CREATE INDEX files_exif_15_file_id_idx ON files_exif_15 USING BTREE(file_id);
--     CREATE INDEX files_exif_15_filetype_idx ON files_exif_15 USING BTREE(filetype);





--files_size
DROP TABLE IF EXISTS files_size CASCADE;
create table files_size (
    file_id integer REFERENCES files(file_id) ON DELETE CASCADE ON UPDATE CASCADE,
    filetype text DEFAULT 'TIF',
    filesize numeric,
    updated_at timestamp with time zone DEFAULT NOW()
);
ALTER TABLE files_size ADD CONSTRAINT filesize_fileid_filetype UNIQUE (file_id, filetype);
CREATE INDEX files_size_file_id_idx ON files_size USING BTREE(file_id);
CREATE INDEX files_size_filetype_idx ON files_size USING BTREE(filetype);



--file_checks
DROP TABLE IF EXISTS file_checks CASCADE;
CREATE TABLE file_checks (
    table_id serial PRIMARY KEY,
    file_id integer REFERENCES files(file_id) ON DELETE CASCADE ON UPDATE CASCADE,
    folder_id integer REFERENCES folders(folder_id) ON DELETE CASCADE ON UPDATE CASCADE,
    file_check text,
    check_results integer,
    check_info text,
    UNIQUE (file_id, file_check),
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX file_checks1_file_id_idx ON file_checks USING BTREE(file_id);
CREATE INDEX file_checks1_file_check_idx ON file_checks USING BTREE(file_check);
CREATE INDEX file_checks1_check_results_idx ON file_checks USING BTREE(check_results);
CREATE INDEX file_checks1_fc_id_idx ON file_checks USING BTREE(check_results, folder_id);
CREATE INDEX file_checks1_ff_id_idx ON file_checks USING BTREE(folder_id, file_id);
CREATE INDEX file_checks1_cf_id_idx ON file_checks USING BTREE(file_check, file_id);

--
--     --file_checks partitioned by id
--     CREATE TABLE file_checks_00 (
--         CHECK (file_id < 200000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_00 ADD CONSTRAINT file_checks_00_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_01 (
--         CHECK (file_id >= 200000::int AND file_id < 400000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_01 ADD CONSTRAINT file_checks_01_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_02 (
--         CHECK (file_id >= 400000::int AND file_id < 600000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_02 ADD CONSTRAINT file_checks_02_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_03 (
--         CHECK (file_id >= 600000::int AND file_id < 800000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_03 ADD CONSTRAINT file_checks_03_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_04 (
--         CHECK (file_id >= 800000::int AND file_id < 1000000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_04 ADD CONSTRAINT file_checks_04_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_05 (
--         CHECK (file_id >= 1000000::int AND file_id < 1200000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_05 ADD CONSTRAINT file_checks_05_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_06 (
--         CHECK (file_id >= 1200000::int AND file_id < 1400000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_06 ADD CONSTRAINT file_checks_06_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_07 (
--         CHECK (file_id >= 1400000::int AND file_id < 1600000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_07 ADD CONSTRAINT file_checks_07_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_08 (
--         CHECK (file_id >= 1600000::int AND file_id < 1800000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_08 ADD CONSTRAINT file_checks_08_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_09 (
--         CHECK (file_id >= 1800000::int AND file_id < 2000000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_09 ADD CONSTRAINT file_checks_09_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_10 (
--         CHECK (file_id >= 2000000::int AND file_id < 2200000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_10 ADD CONSTRAINT file_checks_10_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_11 (
--         CHECK (file_id >= 2200000::int AND file_id < 2400000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_11 ADD CONSTRAINT file_checks_11_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_12 (
--         CHECK (file_id >= 2400000::int AND file_id < 2600000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_12 ADD CONSTRAINT file_checks_12_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_13 (
--         CHECK (file_id >= 2600000::int AND file_id < 2800000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_13 ADD CONSTRAINT file_checks_13_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_14 (
--         CHECK (file_id >= 2800000::int AND file_id < 3000000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_14 ADD CONSTRAINT file_checks_14_fcheck UNIQUE (file_id, file_check);
--
--     CREATE TABLE file_checks_15 (
--         CHECK (file_id >= 3000000::int)
--     ) INHERITS (file_checks);
--
--     ALTER TABLE file_checks_15 ADD CONSTRAINT file_checks_15_fcheck UNIQUE (file_id, file_check);
--
--
--     ----------------------
--     --Function to insert into the specific subtable
--     ----------------------
--
--     CREATE OR REPLACE FUNCTION checks_insert_data() RETURNS TRIGGER AS $$
--     BEGIN
--         IF ( NEW.file_id < 200000::int ) THEN INSERT INTO file_checks_00 VALUES (NEW.*);
--           ELSIF
--           ( NEW.file_id >= 200000::int AND NEW.file_id < 400000::int ) THEN INSERT INTO file_checks_01 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 400000::int AND NEW.file_id < 600000::int ) THEN INSERT INTO file_checks_02 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 600000::int AND NEW.file_id < 800000::int ) THEN INSERT INTO file_checks_03 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 800000::int AND NEW.file_id < 1000000::int ) THEN INSERT INTO file_checks_04 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 1000000::int AND NEW.file_id < 1200000::int ) THEN INSERT INTO file_checks_05 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 1200000::int AND NEW.file_id < 1400000::int ) THEN INSERT INTO file_checks_06 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 1400000::int AND NEW.file_id < 1600000::int ) THEN INSERT INTO file_checks_07 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 1600000::int AND NEW.file_id < 1800000::int ) THEN INSERT INTO file_checks_08 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 1800000::int AND NEW.file_id < 2000000::int ) THEN INSERT INTO file_checks_09 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 2000000::int AND NEW.file_id < 2200000::int ) THEN INSERT INTO file_checks_10 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 2200000::int AND NEW.file_id < 2400000::int ) THEN INSERT INTO file_checks_11 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 2400000::int AND NEW.file_id < 2600000::int ) THEN INSERT INTO file_checks_12 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 2600000::int AND NEW.file_id < 2800000::int ) THEN INSERT INTO file_checks_13 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 2800000::int AND NEW.file_id < 3000000::int ) THEN INSERT INTO file_checks_14 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--           ELSIF
--           ( NEW.file_id >= 3000000::int ) THEN INSERT INTO file_checks_15 VALUES (NEW.*) ON CONFLICT (file_id, file_check) DO UPDATE SET value = NEW.value;
--
--         END IF;
--         RETURN NULL;
--     END;
--     $$ LANGUAGE plpgsql;
--
--
--     ----------------------
--     --Trigger for insert
--     ----------------------
--     CREATE TRIGGER checks_insert_trigger
--     BEFORE INSERT ON file_checks
--     FOR EACH ROW EXECUTE PROCEDURE checks_insert_data();
--
--     --Indices
--     CREATE INDEX file_checks_00_file_id_idx ON file_checks_00 USING BTREE(file_id);
--     CREATE INDEX file_checks_00_file_check_idx ON file_checks_00 USING BTREE(file_check);
--     CREATE INDEX file_checks_00_fc_id_idx ON file_checks_00 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_00_ff_id_idx ON file_checks_00 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_00_cf_id_idx ON file_checks_00 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_01_file_id_idx ON file_checks_01 USING BTREE(file_id);
--     CREATE INDEX file_checks_01_file_check_idx ON file_checks_01 USING BTREE(file_check);
--     CREATE INDEX file_checks_01_fc_id_idx ON file_checks_01 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_01_ff_id_idx ON file_checks_01 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_01_cf_id_idx ON file_checks_01 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_02_file_id_idx ON file_checks_02 USING BTREE(file_id);
--     CREATE INDEX file_checks_02_file_check_idx ON file_checks_02 USING BTREE(file_check);
--     CREATE INDEX file_checks_02_fc_id_idx ON file_checks_02 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_02_ff_id_idx ON file_checks_02 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_02_cf_id_idx ON file_checks_02 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_03_file_id_idx ON file_checks_03 USING BTREE(file_id);
--     CREATE INDEX file_checks_03_file_check_idx ON file_checks_03 USING BTREE(file_check);
--     CREATE INDEX file_checks_03_fc_id_idx ON file_checks_03 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_03_ff_id_idx ON file_checks_03 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_03_cf_id_idx ON file_checks_03 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_04_file_id_idx ON file_checks_04 USING BTREE(file_id);
--     CREATE INDEX file_checks_04_file_check_idx ON file_checks_04 USING BTREE(file_check);
--     CREATE INDEX file_checks_04_fc_id_idx ON file_checks_04 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_04_ff_id_idx ON file_checks_04 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_04_cf_id_idx ON file_checks_04 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_05_file_id_idx ON file_checks_05 USING BTREE(file_id);
--     CREATE INDEX file_checks_05_file_check_idx ON file_checks_05 USING BTREE(file_check);
--     CREATE INDEX file_checks_05_fc_id_idx ON file_checks_05 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_05_ff_id_idx ON file_checks_05 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_05_cf_id_idx ON file_checks_05 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_06_file_id_idx ON file_checks_06 USING BTREE(file_id);
--     CREATE INDEX file_checks_06_file_check_idx ON file_checks_06 USING BTREE(file_check);
--     CREATE INDEX file_checks_06_fc_id_idx ON file_checks_06 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_06_ff_id_idx ON file_checks_06 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_06_cf_id_idx ON file_checks_06 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_07_file_id_idx ON file_checks_07 USING BTREE(file_id);
--     CREATE INDEX file_checks_07_file_check_idx ON file_checks_07 USING BTREE(file_check);
--     CREATE INDEX file_checks_07_fc_id_idx ON file_checks_07 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_07_ff_id_idx ON file_checks_07 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_07_cf_id_idx ON file_checks_07 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_08_file_id_idx ON file_checks_08 USING BTREE(file_id);
--     CREATE INDEX file_checks_08_file_check_idx ON file_checks_08 USING BTREE(file_check);
--     CREATE INDEX file_checks_08_fc_id_idx ON file_checks_08 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_08_ff_id_idx ON file_checks_08 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_08_cf_id_idx ON file_checks_08 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_09_file_id_idx ON file_checks_09 USING BTREE(file_id);
--     CREATE INDEX file_checks_09_file_check_idx ON file_checks_09 USING BTREE(file_check);
--     CREATE INDEX file_checks_09_fc_id_idx ON file_checks_09 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_09_ff_id_idx ON file_checks_09 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_09_cf_id_idx ON file_checks_09 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_10_file_id_idx ON file_checks_10 USING BTREE(file_id);
--     CREATE INDEX file_checks_10_file_check_idx ON file_checks_10 USING BTREE(file_check);
--     CREATE INDEX file_checks_10_fc_id_idx ON file_checks_10 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_10_ff_id_idx ON file_checks_10 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_10_cf_id_idx ON file_checks_10 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_11_file_id_idx ON file_checks_11 USING BTREE(file_id);
--     CREATE INDEX file_checks_11_file_check_idx ON file_checks_11 USING BTREE(file_check);
--     CREATE INDEX file_checks_11_fc_id_idx ON file_checks_11 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_11_ff_id_idx ON file_checks_11 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_11_cf_id_idx ON file_checks_11 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_12_file_id_idx ON file_checks_12 USING BTREE(file_id);
--     CREATE INDEX file_checks_12_file_check_idx ON file_checks_12 USING BTREE(file_check);
--     CREATE INDEX file_checks_12_fc_id_idx ON file_checks_12 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_12_ff_id_idx ON file_checks_12 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_12_cf_id_idx ON file_checks_12 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_13_file_id_idx ON file_checks_13 USING BTREE(file_id);
--     CREATE INDEX file_checks_13_file_check_idx ON file_checks_13 USING BTREE(file_check);
--     CREATE INDEX file_checks_13_fc_id_idx ON file_checks_13 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_13_ff_id_idx ON file_checks_13 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_13_cf_id_idx ON file_checks_13 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_14_file_id_idx ON file_checks_14 USING BTREE(file_id);
--     CREATE INDEX file_checks_14_file_check_idx ON file_checks_14 USING BTREE(file_check);
--     CREATE INDEX file_checks_14_fc_id_idx ON file_checks_14 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_14_ff_id_idx ON file_checks_14 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_14_cf_id_idx ON file_checks_14 USING BTREE(file_check, file_id);
--
--     CREATE INDEX file_checks_15_file_id_idx ON file_checks_15 USING BTREE(file_id);
--     CREATE INDEX file_checks_15_file_check_idx ON file_checks_15 USING BTREE(file_check);
--     CREATE INDEX file_checks_15_fc_id_idx ON file_checks_15 USING BTREE(check_results, folder_id);
--     CREATE INDEX file_checks_15_ff_id_idx ON file_checks_15 USING BTREE(folder_id, file_id);
--     CREATE INDEX file_checks_15_cf_id_idx ON file_checks_15 USING BTREE(file_check, file_id);


--file_postprocessing
DROP TABLE IF EXISTS file_postprocessing CASCADE;
CREATE TABLE file_postprocessing (
    file_id integer REFERENCES files(file_id) ON DELETE CASCADE ON UPDATE CASCADE,
    post_step text,
    post_results integer,
    post_info text,
    updated_at timestamp with time zone DEFAULT NOW()
);
ALTER TABLE file_postprocessing ADD CONSTRAINT fpp_fileid_and_poststep UNIQUE (file_id, post_step);
CREATE INDEX file_postprocessing_file_id_idx ON file_postprocessing USING BTREE(file_id);
CREATE INDEX file_postprocessing_post_step_idx ON file_postprocessing USING BTREE(post_step);
CREATE INDEX file_postprocessing_check_results_idx ON file_postprocessing USING BTREE(post_results);



--file_names - valid filenames for a project
DROP TABLE IF EXISTS file_names_valid CASCADE;
CREATE TABLE file_names_valid (
    tableid serial PRIMARY KEY,
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    filename text,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX fnamesvalid_project_id_idx on file_names_valid USING BTREE(project_id);
CREATE INDEX fnamesvalid_fname_idx on file_names_valid USING BTREE(filename);


--old_names
DROP VIEW IF EXISTS dupe_elsewhere;
CREATE VIEW dupe_elsewhere AS
    (
    SELECT
           f.file_id, f.file_name, COALESCE(p.project_alias, p.project_id::text) || ':' || fol.project_folder as folder, p.project_id::text
    FROM
         files f,
         folders fol,
         projects p
    WHERE
          p.project_id = fol.project_id
          and fol.folder_id = f.folder_id

    UNION

    SELECT
        vfcu_media_file_id as file_id,
           replace(replace(file_name, '.tif', ''), '.TIF', '') as file_name,
           'DAMS:' || project_cd || ':' || dams_uan as folder, project_cd as project_id
    FROM
        dams_cdis_file_status_view_dpo
    WHERE
        file_name ILIKE '%.tif'
);


--projects_stats
DROP TABLE IF EXISTS projects_stats CASCADE;
CREATE TABLE projects_stats (
    tid serial PRIMARY KEY,
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    start_date date,
    end_date date,
    collex_total integer,
    collex_to_digitize integer,
    collex_ready integer,
    objects_digitized integer,
    images_taken integer,
    images_in_dams integer,
    images_in_cis integer,
    images_public integer,
    transcription integer,
    transcription_qc integer,
    transcription_in_cis integer,
    no_records_in_cis integer,
    no_records_in_collexweb integer,
    no_records_in_collectionssiedu integer,
    no_records_in_gbif integer,
    avg_file_size numeric,
    total_file_size numeric,
    avg_rawfile_size numeric,
    total_rawfile_size numeric,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX projects_stats_pid_idx on projects_stats USING BTREE(project_id);
CREATE INDEX projects_updated_at_idx on projects_stats USING BTREE(updated_at);


--For pivot tables
CREATE extension tablefunc;



---------------------------
--QC tables
---------------------------
--qc_settings
DROP TABLE IF EXISTS qc_settings CASCADE;
create table qc_settings (
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE PRIMARY KEY,
    qc_level text DEFAULT 'Normal',
    qc_percent numeric DEFAULT 10,
    qc_critical_threshold numeric DEFAULT 0,
    qc_major_threshold numeric DEFAULT 0.015,
    qc_minor_threshold numeric DEFAULT 0.04,
    qc_normal_percent numeric DEFAULT 10,
    qc_reduced_percent numeric DEFAULT 5,
    qc_tightened_percent numeric DEFAULT 40
);
CREATE INDEX qc_settings_pid_idx ON qc_settings USING BTREE(project_id);



--qc_lots
DROP TABLE IF EXISTS qc_lots CASCADE;
DROP SEQUENCE IF EXISTS qc_lots_id_seq;
CREATE SEQUENCE qc_lots_id_seq MINVALUE 100;
create table qc_lots (
    qc_lot_id integer NOT NULL DEFAULT nextval('qc_lots_id_seq') PRIMARY KEY,
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    qc_lot_title text NOT NULL,
    qc_lot_date date[] NOT NULL,
    qc_lot_percent numeric DEFAULT 10,
    qc_pass boolean,
    qc_level text DEFAULT 'Normal',
    qc_reason text,
    qc_approved_by integer,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX qc_lots_qcid_idx ON qc_lots USING BTREE(qc_lot_id);

CREATE TRIGGER trigger_updated_at_qclots
  BEFORE UPDATE ON qc_lots
  FOR EACH ROW
  EXECUTE PROCEDURE updated_at_files();



--qc_lots_folders
DROP TABLE IF EXISTS qc_lots_folders CASCADE;
create table qc_lots_folders (
    qc_lot_id integer NOT NULL REFERENCES qc_lots(qc_lot_id) ON DELETE CASCADE ON UPDATE CASCADE,
    folder_id integer NOT NULL REFERENCES folders(folder_id) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX qc_lots_folders_qclid_idx ON qc_lots_folders USING BTREE(qc_lot_id);
CREATE INDEX qc_lots_folders_fid_idx ON qc_lots_folders USING BTREE(folder_id);



--qc_lots_files
DROP TABLE IF EXISTS qc_lots_files CASCADE;
create table qc_lots_files (
    qc_lot_id integer NOT NULL REFERENCES qc_lots(qc_lot_id) ON DELETE CASCADE ON UPDATE CASCADE,
    file_id integer NOT NULL REFERENCES files(file_id) ON DELETE CASCADE ON UPDATE CASCADE,
    qc_critical boolean DEFAULT NULL,
    qc_major boolean DEFAULT NULL,
    qc_minor boolean DEFAULT NULL,
    qc_info text,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX folders_qc_files_filed_idx ON qc_lots_files USING BTREE(file_id);

CREATE TRIGGER trigger_updated_at_qcfiles
  BEFORE UPDATE ON qc_lots_files
  FOR EACH ROW
  EXECUTE PROCEDURE updated_at_files();


--qc_users
DROP TABLE IF EXISTS qc_users CASCADE;
CREATE TABLE qc_users (
    user_id serial primary key,
    username text,
    full_name text,
    pass text,
    user_active boolean DEFAULT 't',
    is_admin boolean DEFAULT 'f'
);
CREATE INDEX qc_users_un_idx ON qc_users USING BTREE(username);
CREATE INDEX qc_users_up_idx ON qc_users USING BTREE(pass);
CREATE INDEX qc_users_ua_idx ON qc_users USING BTREE(user_active);


DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE users (
    uid uuid NOT NULL DEFAULT uuid_generate_v4() primary key,
	user_id serial,
    username text,
    full_name text,
    pass text,
    user_active boolean DEFAULT 't',
    is_admin boolean DEFAULT 'f'
);
CREATE INDEX users_un_idx ON users USING BTREE(uid);
CREATE INDEX users_un_idx ON users USING BTREE(username);
CREATE INDEX users_up_idx ON users USING BTREE(pass);
CREATE INDEX users_ua_idx ON users USING BTREE(user_active);

-- delete from users;
-- insert into users (user_id, username, pass, user_active, is_admin, full_name) (select user_id, username, pass, user_active, is_admin, full_name from qc_users);


--projects assigned to users
DROP TABLE IF EXISTS qc_projects CASCADE;
create table qc_projects (
    id serial PRIMARY KEY,
    project_id integer REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    user_id integer REFERENCES qc_users(user_id) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX qc_projects_fid_idx ON qc_projects USING BTREE(project_id);
CREATE INDEX qc_projects_pid_idx ON qc_projects USING BTREE(user_id);




--qc_users_cookies
DROP TABLE IF EXISTS qc_users_cookies CASCADE;
CREATE TABLE qc_users_cookies (
    user_id serial REFERENCES qc_users(user_id) ON DELETE CASCADE ON UPDATE CASCADE,
    cookie text,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX qc_users_cookies_un_idx ON qc_users_cookies USING BTREE(user_id);
CREATE INDEX qc_users_cookies_c_idx ON qc_users_cookies USING BTREE(cookie);


--qc_folders
DROP TABLE IF EXISTS qc_folders CASCADE;
create table qc_folders (
    folder_id integer NOT NULL REFERENCES folders(folder_id) ON DELETE CASCADE ON UPDATE CASCADE PRIMARY KEY ,
    qc_status integer DEFAULT 9,
    qc_by integer,
    qc_ip text,
    qc_info text,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX qc_folders_fid_idx ON qc_folders USING BTREE(folder_id);
CREATE INDEX qc_folders_qby_idx ON qc_folders USING BTREE(qc_by);

CREATE TRIGGER trigger_updated_qc_folders
  BEFORE UPDATE ON qc_folders
  FOR EACH ROW
  EXECUTE PROCEDURE updated_at_files();


--qc_files
DROP TABLE IF EXISTS qc_files CASCADE;
create table qc_files (
    folder_id integer NOT NULL REFERENCES qc_folders(folder_id) ON DELETE CASCADE ON UPDATE CASCADE,
    file_id integer NOT NULL REFERENCES files(file_id) ON DELETE CASCADE ON UPDATE CASCADE,
    file_qc integer DEFAULT 9,
    qc_info text,
    qc_by integer,
    qc_ip text,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX qc_files_fid_idx ON qc_files USING BTREE(file_id);

CREATE TRIGGER trigger_updated_qc_files
  BEFORE UPDATE ON qc_files
  FOR EACH ROW
  EXECUTE PROCEDURE updated_at_files();








--REPORTS
DROP TABLE IF EXISTS data_reports CASCADE;
create table data_reports (
    report_id uuid NOT NULL DEFAULT uuid_generate_v4() PRIMARY KEY,
    project_id int NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    report_title text NOT NULL,
	report_title_brief text,
    query text NOT NULL,
    query_api text NOT NULL,
    query_updated text NOT NULL,
    updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX data_reports_rid_idx ON data_reports USING BTREE(report_id);
CREATE INDEX data_reports_pid_idx ON data_reports USING BTREE(project_id);

CREATE TRIGGER trigger_data_reports
  BEFORE UPDATE ON data_reports
  FOR EACH ROW
  EXECUTE PROCEDURE updated_at_files();





-- API Keys
DROP TABLE IF EXISTS api_keys CASCADE;
create table api_keys (
    table_id uuid NOT NULL DEFAULT uuid_generate_v4() PRIMARY KEY,
    uid UUID NOT NULL REFERENCES users(uid) ON DELETE CASCADE ON UPDATE CASCADE,
    key UUID NOT NULL,
    expires_on timestamp with time zone,
	usage_rate int NOT NULL DEFAULT 100,
	updated_at timestamp with time zone DEFAULT NOW()
);
CREATE INDEX akeys_uid_idx ON api_keys USING BTREE(uid);
CREATE INDEX akeys_key_idx ON api_keys USING BTREE(key);

CREATE TRIGGER trigger_api_keys
  BEFORE UPDATE ON api_keys
  FOR EACH ROW
  EXECUTE PROCEDURE updated_at_files();


