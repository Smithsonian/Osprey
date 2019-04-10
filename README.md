# DPO MD FileCheck

MD FileCheck is a system that checks the images produced by vendors in mass digitization projects by the Digitization Program Office, OCIO, Smithsonian. The system checks that the files pass a number of tests and displays the results in a Shiny dashboard. This allows the vendor, the project manager, and the unit to monitor the progress and detect problems early.

## Components

The system has two components:

 * [filecheck](filecheck) - Python3 script that runs the checks against mounted shares. Results are written to a Postgres database.
 * [dashboard](dashboard) - R/Shiny dashboard that reads the Postgres database and displays the results.

The system assumes:

* Each image has a pair of files: a raw file (specific format dependent on the camera(s) used) and a tif file
* Each folder in the mount has a pair of subfolders: `tifs` and `raws`
  * If there are JPG files, these are stored in a subfolder called `jpgs`
