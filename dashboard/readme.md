## Setup

The app currently expects a Postgres database. Install and populate the database according to the instructions in [database/tables.sql](../database/tables.sql).

To install the required environment and modules to the default location:

```bash
mkdir /var/www/app
cd /var/www/app
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
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

Setup apache2/httpd as described in the [web_server](../web_server) folder
