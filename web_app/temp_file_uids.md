update files f , folders fol set f.folder_uid = fol.folder_uid where f.folder_id = fol.folder_id;
update files set file_uid = uuid_v4s();

update folders_md5 fm, folders fol set fol.folder_uid = fm.folder_uid where fol.folder_id = f.folder_id;

update qc_folders qc, folders fol set qc.folder_uid = fol.folder_uid where qc.folder_id = fol.folder_id;


update folders_badges qc, folders fol set qc.folder_uid = fol.folder_uid where qc.folder_id = fol.folder_id;


update qc_files qc, folders fol set qc.folder_uid = fol.folder_uid where qc.folder_id = fol.folder_id;
update qc_files qc, files f set qc.file_uid = f.file_uid where qc.file_id = f.file_id;

