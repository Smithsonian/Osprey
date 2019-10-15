#!/usr/bin/env python3
#
# Check if image is on focus
#  based on https://www.pyimagesearch.com/2015/09/07/blur-detection-with-opencv/
# Version 0.1
#
import argparse, cv2, sys

#Get imagename
img_file = sys.argv[1]

def variance_of_laplacian(image):
    return cv2.Laplacian(image, cv2.CV_64F).var()
 
image = cv2.imread(img_file)
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
fm = variance_of_laplacian(gray)

if fm < 100:
    result = "Image blurry"
else:
    result = "Image not blurry"


print("{};{}".format(fm.round(5), result))
