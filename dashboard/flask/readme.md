## Run Locally

To install the required modules using pip:

> python3 -m pip install -r requirements.txt

Then, run the API:

> ./app.py

or:

> python3 app.py

which will start the service at `http://localhost:5000/`.

## To Install

 * Create the folder `/var/www/app`
 * Install `virtualenv`: `python3 -m pip install virtualenv`
 * `cd /var/www/app` 
 * `python3 -m venv venv`
 * `source env/bin/activate`
 * `python3 -m pip install -r requirements.txt`
 * `deactivate`
 * Setup apache2/httpd as described in the [web_server](../web_server) folder
