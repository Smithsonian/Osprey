# ID of the project, must exist in the database already
project_id = ""


# List of paths where the folders are stored
project_paths = []


# Temp folder, usually /tmp
# No trailing slash
tmp_folder = "/tmp"


# Subfolders of files
main_files_path = "tifs"
raw_files_path = "raws"
derivative_files_path = "jpgs"


# Postgres database and rw user,
db_host = ""
db_db = ""
db_user = ""
db_password = ""


# How to split to parse the date, return the date in format 'YYYY-MM-DD'
def folder_date(folder_name):
    # Example as PREFIX-YYYYMMDD
    folder_date = folder_name.split('PREFIX-')[1]
    formatted_date = "{}-{}-{}".format(folder_date[0:4], folder_date[4:6], folder_date[6:8])
    return formatted_date


####################################################################
# Project checks to run
####################################################################
project_file_checks = ["raw_pair", "unique_file", "jhove", "magick",
                       "tifpages", "tif_compression", "md5_hash"]
# The options are:
#
# - raw_pair: Is there a raw file in the 'raw_files_path'
# - valid_name: Filename is in the list of allowed names
# - unique_file: Name is not repeated in the project
# - old_name: Check name against the old_names table
# - jhove: Run jhove validation
# - magick: Run imagemagick validation
# - tifpages: Check the number of pages in the tif, typically a thumbnail
# - tif_compression: Check if tif is compressed using LZW
# - derivative: Check for a derivative file in 'derivative_files_path'
# - md5_hash: Check if the subfolders have md5 files
#
# Specify these options below:
# - prefix: Filename has the required prefix
# - suffix: Filename has the required suffix
# - stitched_jpg: There is a stitched JPG of two other files, settings below
####################################################################


# Filename prefix required by selecting 'prefix' above
filename_prefix = None


# Filename suffix required by selecting 'suffix' above
filename_suffix = None


# Should the names match a db?
files_db = False
# How to find the list of valid names
# this has to be a valid query that will 
# be used in a subquery
filename_pattern_query = "SELECT COUNT(*) as no_records FROM (SELECT file_name FROM filename_table WHERE project_id = 100 AND file_name = '{}') a"


# How long to sleep between loops
# Set to False to run only once
# sleep = False
sleep = 180


# Path for JHOVE in system
jhove_path = "/usr/local/jhove/jhove"


# Path of where to save the JPG previews and size
jpg_previews = ""
# Set previews_size = 'full' to keep the same size as the main image
previews_size = "full"


# stitched_jpg
# Check for stitched jpg files from two mains
jpgstitch_original_1 = ""
jpgstitch_original_2 = ""
jpgstitch_new = ""


# Scripts to run before or after checking the files. Set to None if it won't be used.
pre_script = None
post_script = None
