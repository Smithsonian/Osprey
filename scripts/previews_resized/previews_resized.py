#!/usr/bin/env python3
#
from PIL import Image
import glob
import os
from pathlib import Path
import sys
from pqdm.processes import pqdm


if len(sys.argv) == 4:
    folder_path = sys.argv[1]
    width = int(sys.argv[2])
    no_workers = int(sys.argv[3])
else:
    print("Wrong number of args")


# Remove DecompressionBombWarning due to large files
# by using a large threshold
# https://github.com/zimeon/iiif/issues/11
Image.MAX_IMAGE_PIXELS = 1000000000


path_resized = "{}/{}".format(folder_path, width)
if not os.path.exists(path_resized):
    os.makedirs(path_resized)

files = glob.glob("{}/*.jpg".format(folder_path))

def resize_img(filename):
    filename_stem = Path(filename).stem
    # print("Working on: {}".format(filename_stem))
    img = Image.open(filename)
    wpercent = (int(width) / float(img.size[0]))
    hsize = int((float(img.size[1]) * float(wpercent)))
    img = img.resize((int(width), hsize), Image.LANCZOS)
    filename = "{}/{}.jpg".format(path_resized, filename_stem)
    img.save(filename, icc_profile=img.info.get('icc_profile'))
    return filename


result = pqdm(files, resize_img, n_jobs=no_workers)

