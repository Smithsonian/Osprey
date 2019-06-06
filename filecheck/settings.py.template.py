#Where the folders are mounted
project_paths = []
project_id = ""
project_checks = ["file_pair","tif_size","raw_size","magick","jhove","jpg", "unique_file","tifpages"]
special_checks = []


folder_name = ""
folder_date = ""


#Postgres database and rw user
db_host = ""
db_db = ""
db_user = ""
db_password = ""


#Raw files extension
raw_files = "IIQ"
tif_files_path = "tifs"
raw_files_path = "raws"
jpg_files_path = "jpgs"
wav_files_path = "wavs"


#Should the names match a db?
files_db = True
#How to find the list of valid names
# this has to be a valid query that will 
# be used in a subquery
filename_pattern_query = "SELECT COUNT(*) as no_records FROM (SELECT CONCAT('AC0433-', LPAD(file_name::text, 6, '0'), '%') AS file_name FROM valid_names WHERE project_id = 104) a WHERE a.file_name LIKE '{}%'"


#TIF file min and max size, in bytes
tif_size_min = 70000000
tif_size_max = 390000000

#RAW file min and max size, in bytes
raw_size_min = 50000000
raw_size_max = 300000000


#How long to sleep between loops
sleep = 180


#Path for JHOVE
jhove_path = ""


#How many parallel workers
no_workers = 1
no_workers_night = 4


#JPG location
jpg_previews = ""


use_item_id = False
item_id = ""


#Ignore files with this string anywhere in the filename
ignore_string = ""


oldname_subquery = " AND file_folder NOT IN (SELECT split_part(project_folder, '/', 2) FROM folders WHERE folder_id = {})"


#Wav files
wav_filetype = "wav"
wav_samprate = ""
wav_channels = ""
wav_bits = ""
