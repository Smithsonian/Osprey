#!flask/bin/python
#
# Server for images for Osprey Dashboard from separate server
#
# Import flask
from flask import Flask
from flask import Response
from flask import render_template
from flask import request
from flask import jsonify
from flask import send_file
# caching
from flask_caching import Cache

import logging
import locale
import os

from PIL import Image

import simplejson as json
import psycopg2
import psycopg2.extras

import settings

site_ver = "1.0"

# Logging
logging.basicConfig(filename='app.log',
                    level=logging.DEBUG,
                    filemode='a',
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%y-%m-%d %H:%M:%S'
                    )
# define a Handler which writes INFO messages or higher to the sys.stderr
console = logging.StreamHandler()
console.setLevel(logging.INFO)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)
# Set locale for number format
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')


# Cache config
config = {
    "DEBUG": True,  # some Flask specific configs
    "CACHE_TYPE": "FileSystemCache",  # Flask-Caching related configs
    "CACHE_DIR": "{}/cache".format(os.getcwd()),
    "CACHE_DEFAULT_TIMEOUT": 300
}
app = Flask(__name__)
# tell Flask to use the above defined config
app.config.from_mapping(config)
cache = Cache(app)


# From http://flask.pocoo.org/docs/1.0/patterns/apierrors/
class InvalidUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        return rv


@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@app.errorhandler(404)
def page_not_found(e):
    logging.error(e)
    data = json.dumps({'error': "route not found"})
    return Response(data, mimetype='application/json'), 404


@app.errorhandler(500)
def page_not_found(e):
    logging.error(e)
    data = json.dumps({'error': "system error"})
    return Response(data, mimetype='application/json'), 500


def preprocess(token):
    tokens = token.split(" ")
    for i, t in enumerate(tokens):
        if ")" in t or "(" in t:
            tokens[i] = ''
    token = " ".join(tokens)
    if token.endswith("."):
        token = token[:-1]
    return token.lower().lstrip().rstrip()


# Database
try:
    conn = psycopg2.connect(host=settings.host,
                            database=settings.database,
                            user=settings.user,
                            password=settings.password)
except psycopg2.Error as e:
    logging.error(e)
    raise InvalidUsage('System error', status_code=500)


@cache.memoize()
def query_database(query_template, parameters="", logging=None):
    try:
        with open(query_template) as f:
            query = f.read()
    except IOError as e:
        logging.error(e)
        return None
    logging.info("parameters: {}".format(parameters))
    logging.info("query: {}".format(query))
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Run query
    try:
        cur.execute(query, parameters)
        logging.info("cur.query: {}".format(cur.query))
    except psycopg2.ProgrammingError as e:
        logging.error("cur.query: {} | p.error: {}".format(cur.query, e))
        return None
    except psycopg2.Error as e:
        logging.error("cur.query: {} | error: {}".format(cur.query, e))
        return None
    logging.info(cur.rowcount)
    if cur.rowcount == -1:
        data = None
    else:
        data = cur.fetchall()
    return data


###################################
# System routes
###################################
@cache.memoize()
@app.route('/', methods=['GET', 'POST'])
def home_system():
    """Main homepage for the system"""
    return render_template('home.html')


#################################
# MassDigi-specific routes
#################################
@cache.memoize()
@app.route('/previewimage/<int:file_id>/', methods=['GET'], strict_slashes=False)
def get_preview(file_id=None):
    """Return image previews from Mass Digi Projects."""
    if file_id is None:
        raise InvalidUsage('file_id missing', status_code=400)
    #
    try:
        file_id = int(file_id)
    except:
        raise InvalidUsage('invalid file_id value', status_code=400)
    data = query_database('queries/get_folder_id.sql', {'file_id': file_id}, logging=logging)
    logging.info("data: {}".format(data))
    if data == None:
        filename = "static/na.jpg"
        return send_file(filename, mimetype='image/jpeg')
    elif len(data) == 0:
        filename = "static/na.jpg"
        return send_file(filename, mimetype='image/jpeg')
    else:
        try:
            folder_id = data[0]
            max = request.args.get('max')
            if max is not None:
                width = max
            else:
                width = request.args.get('size')
            if width is None:
                filename = "static/mdpp_previews/folder{}/{}.jpg".format(folder_id['folder_id'], file_id)
            else:
                filename = "static/mdpp_previews/folder{}/{}.jpg".format(folder_id['folder_id'], file_id)
                img = Image.open(filename)
                wpercent = (int(width) / float(img.size[0]))
                hsize = int((float(img.size[1]) * float(wpercent)))
                img = img.resize((int(width), hsize), Image.ANTIALIAS)
                filename = "/tmp/{}_{}.jpg".format(file_id, width)
                img.save(filename)
        except:
            filename = "static/na.jpg"
    if not os.path.isfile(filename):
        filename = "static/na.jpg"
    #
    logging.error(filename)
    try:
        return send_file(filename, mimetype='image/jpeg')
    except:
        return send_file("static/na.jpg", mimetype='image/jpeg')


#####################################
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
