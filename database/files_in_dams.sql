--Update the database to indicate the files were ingested in the DAMS

--Check if the file is in the DAMS view dams_vfcu_file_view_dpo
UPDATE file_postprocessing
SET post_results = 0 WHERE 
post_step = 'in_dams'
AND file_id in 
    (
        SELECT 
            file_id 
        FROM 
            (
                SELECT
                    f.file_id
                FROM 
                    dams_vfcu_file_view_dpo d,
                    files f
                WHERE 
                    d.project_cd = 'nmnh_palbio2' and 
                    --project_cd = 'nmnh_ento_bees2' and
                    d.media_file_name = f.file_name || '.tif' AND
                    f.folder_id = 690 ) a
    );


--Set folder
UPDATE 
    folders
SET 
    delivered_to_dams = 1
WHERE
    folder_id = 764;


--Update table with DAMS uan
UPDATE files f SET dams_uan = d.dams_uan 
    FROM
    (
    SELECT
        f.file_id,
        d.dams_uan
    FROM 
        dams_cdis_file_status_view_dpo d,
        files f
    WHERE 
        d.project_cd = 'nmnh_palbio2' and 
        --project_cd = 'nmnh_ento_bees2' and
        d.file_name = f.file_name || '.tif' AND
        f.folder_id = 690 ) d
    WHERE f.file_id = d.file_id;
