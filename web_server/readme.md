# apache2/httpd configuration for the app

Based on the [flask mod_wsgi documentation](https://flask.palletsprojects.com/en/2.0.x/deploying/mod_wsgi/):

## Install required httpd/apache and wsgi module

In RHEL:
```bash
sudo dnf install mod_wsgi httpd
```

In Ubuntu:
```bash
sudo apt-get install libapache2-mod-wsgi-py3
sudo a2enconf mod-wsgi
sudo a2enmod rewrite
```

## Configuration

Add the configuration, adapting it to your system, from these files:

* apache.config - Replace the values in brackets and add to your apache/httpd config
  * In RHEL:
    * Config in: `/etc/httpd/conf.d/[site].conf`
    * Restart httpd: `sudo systemctl restart httpd`
  * In Ubuntu:
    * Config in: `/etc/apache2/sites-available/[site].conf`
    * Enable site: `sudo a2ensite [site]`
    * Restart apache2: `sudo service apache2 restart`
* app.wsgi - the WSGI script to place in the path specified in the config file that runs the Flask app

Check the web server documentation for details.

Note: The files use `/var/www/app` as the root of the app.
