# Osprey

Osprey is a system that checks the images produced by vendors in mass
digitization projects by the Collections Digitization program of the
Digitization Program Office, OCIO, Smithsonian.

![DPO Logo](https://github.com/Smithsonian/Osprey/assets/2302171/fa136270-943d-47f3-8a86-2eb6660b2913)

https://dpo.si.edu/

The system checks that the files pass a number of tests and displays
the results in a web dashboard. This allows the vendor, the
project manager, and the unit to monitor the progress and detect
problems early.

## Osprey Dashboard

This repo hosts the code for the dashboard, which presents the progress in each project and highlights any issues in the files.

![Main dashboard](https://user-images.githubusercontent.com/2302171/200641626-1f560bac-6245-447d-9a1f-b72249a47ca9.png)

![Example Project](https://user-images.githubusercontent.com/2302171/200641552-ac89022c-e79e-421d-9ac9-c120cbdb20a5.png)

## File Checks

The [Osprey Worker](https://github.com/Smithsonian/Osprey_Worker/) runs in Linux and updates the dashboard via an API (see below). The Worker can be configured to run one or more of these checks:

 * unique_file - Unique file name in the project
 * raw_pair - There is a raw file paired in a subfolder (*e.g.* tifs and raws (.eip/.iiq) subfolders)
 * jhove - The file is a valid image according to [JHOVE](https://jhove.openpreservation.org/)
 * tifpages - The tif files don't contain an embedded thumbnail, or more than one image per file
 * magick - The file is a valid image according to [Imagemagick](https://imagemagick.org/)
 * tif_compression - The tif file is compressed using LZW to save disk space

Other file checks can be added. Documentation to be added. 

## Setup

The app runs in Python using the Flask module and requires a MySQL database. Install and populate the database according to the instructions in [database/tables.sql](https://github.com/Smithsonian/Osprey_Misc/tree/main/database).

To install the required environment and modules to the default location (`/var/www/app`):

```bash
mkdir /var/www/app
cd /var/www/app
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Then, test the API by running the main file:

```bash
./app.py
```

or:

```bash
python3 app.py
```

which will start the service at `http://localhost:5000/`.

Update permissions:

```bash
deactivate
sudo chown -R apache:apache /var/www/app
```

Setup apache2/httpd as described in the [web_server](web_server) folder

## API

The application includes an API with these routes:

 * `/api/`: Print available routes in JSON
 * `/api/files/<file_id>`: Get the details of a file by its `file_id`
 * `/api/folders/<folder_id>`: Get the details of a folder and the list of files
 * `/api/folders/qc/<folder_id>`: Get the details of a folder and the list of files from QC
 * `/api/projects/`: Get the list of projects in the system
 * `/api/projects/<project_alias>`: Get the details of a project by specifying the project_alias
 * `/api/reports/<report_id>/`: Get the data from a project report

## Components

The system has two related repos:

 * [Osprey Worker](https://github.com/Smithsonian/Osprey_Worker/) - Python tool that runs a series of checks on folders. Results are sent to the dashboard via an HTTP API to be saved to the database.
 * [Osprey Misc](https://github.com/Smithsonian/Osprey_Misc/) - Database and scripts.

## License

Available under the Apache License 2.0. Consult the [LICENSE](LICENSE) file for details.
