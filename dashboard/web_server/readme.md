# apache2/httpd configuration for the app

Based on the [flask mod_wsgi documentation](https://flask.palletsprojects.com/en/2.0.x/deploying/mod_wsgi/):

 * apache.config - Replace the values in brackets and add to your apache2/httpd config
 * app.wsgi - the WSGI script to place in the path specified in the config file that runs the Flask app

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
