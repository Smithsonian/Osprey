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


## Setup

The app currently expects a Postgres database. Install and populate the database according to the instructions in [database/tables.sql](https://github.com/Smithsonian/Osprey_Misc/tree/main/database).

To install the required environment and modules to the default location:

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

## Components

The system has two related repos:

 * [Osprey Worker](https://github.com/Smithsonian/Osprey_Worker/) - Python tool that runs a series of checks on folders. Results are sent to the dashboard via an HTTP API to be saved to the database.
 * [Osprey Misc](https://github.com/Smithsonian/Osprey_Misc/) - Database and scripts.

## License

Available under the Apache License 2.0. Consult the [LICENSE](LICENSE) file for details.
