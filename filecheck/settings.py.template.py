#ID of the project
project_id = ""

#List of paths where the folders to check are
project_paths = []

#List of shares used in the project,
# each in its own list: ["mount point", "server"]
project_shares = []

tmp_folder = "/tmp"


##################################
#Postgres database and rw user
##################################
db_host = ""
db_db = ""
db_user = ""
##################################




##################################
#What kind of product will be produced in the project
##################################
project_type = "tif"
# Options are:
# - tif
# - wav
##################################



##################################
#Project checks to run
##################################
project_file_checks = ["raw_pair","magick","jhove","unique_file","tifpages"]
#For TIFS:
# - raw_pair: The raw file with the extension in 'raw_files' paired to the tif
# - tif_size: Size of the tif file
# - raw_size: Size of the raw file
# - jpg: Check for a jpg file for each tif
# - tifpages: Check the number of pages in the tif
# - magick: Run imagemagick validation
# - itpc: Check for valid ITPC metadata, not yet implemented
#
#For WAVS:
# - filetype: If the filetype matches 'wav_filetype'
# - samprate: If sampling rate matches 'wav_samprate'
# - channels: If number of channels match 'wav_channels'
# - bits: If bitrate matches 'wav_bits'
#
#For either:
# - jhove: Run jhove validation
# - unique_file: Name is not repeated in the project
# - valid_name: Check if the filename is in the list of allowed names
# - old_name: Check name against the old_names table
##################################


#Special (rare) checks
special_checks = []

folder_name = ""

#How to split to parse the date, return the date in format 'YYYY-MM-DD'
def folder_date(folder_name):
    folder_date = folder_name.split('SG-CGA-Druse-')[1]
    formatted_date = "{}-{}-{}".format(folder_date[0:4], folder_date[4:6], folder_date[6:8])
    return formatted_date



#Raw files extension
raw_files = "iiq"

#Subfolder of files
tif_files_path = "tifs"
raw_files_path = "raws"
jpg_files_path = "jpgs"
wav_files_path = "wavs"


#Should the names match a db?
files_db = False
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
jhove_path = "/home/villanueval/jhove/jhove"


#How many parallel workers
# no_workers = 1
# no_workers_night = 4



#JPG Previews location and size
jpg_previews = ""
#Set previews_size = 'full' to keep the same size as the TIF
previews_size = 1000


#Ignore files with this string anywhere in the filename
ignore_string = None


#Wav files
# wav_filetype = "wav"
# wav_samprate = ""
# wav_channels = ""
# wav_bits = ""


del_folders = True
