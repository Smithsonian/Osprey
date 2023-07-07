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
from flask import redirect
# caching
from flask_caching import Cache

import logging
import locale
import os

from PIL import Image

# MySQL
import pymysql

import simplejson as json

import settings

site_ver = "1.1"

# Logging
logfile = 'app.log'
logging.basicConfig(filename=logfile, filemode='a', level=logging.DEBUG,
                    format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
                    datefmt='%y-%b-%d %H:%M:%S')
logger = logging.getLogger("web_osprey")

logging.info("site_ver = {}".format(site_ver))

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


# def query_database(query_template, parameters="", logging=None):
#     try:
#         conn = pymysql.connect(host=settings.host,
#                                user=settings.user,
#                                password=settings.password,
#                                database=settings.database,
#                                port=settings.port,
#                                charset='utf8mb4',
#                                autocommit=True,
#                                cursorclass=pymysql.cursors.DictCursor)
#         cur = conn.cursor()
#     except pymysql.Error as e:
#         logging.error(e)
#         raise InvalidUsage('System error')
#     try:
#         with open(query_template) as f:
#             query = f.read()
#     except IOError as e:
#         logging.error(e)
#         return None
#     logging.info("parameters: {}".format(parameters))
#     logging.info("query: {}".format(query))
#     # Run query
#     try:
#         cur.execute(query, parameters)
#     except Exception as e:
#         logging.error("cur.query: {} | p.error: {}".format(cur.query, e))
#         return None
#     except Exception as e:
#         logging.error("cur.query: {} | error: {}".format(cur.query, e))
#         return None
#     logging.info(cur.rowcount)
#     if cur.rowcount == -1:
#         data = None
#     else:
#         data = cur.fetchall()
#     cur.close()
#     conn.close()
#     return data

def query_database(query, parameters=None):
    logging.info("parameters: {}".format(parameters))
    logging.info("query: {}".format(query))
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               password=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               autocommit=True,
                               cursorclass=pymysql.cursors.DictCursor)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error("Error in connection: {}".format(e))
        raise InvalidUsage('System error')
    # Run query
    try:
        if parameters is None:
            cur.execute(query)
        else:
            cur.execute(query, parameters)
    except Exception as e:
        logging.error("cur.query: {} | p.error: {}".format(cur.query, e))
        return None
    logging.info(cur.rowcount)
    if cur.rowcount == -1:
        data = None
    else:
        data = cur.fetchall()
    cur.close()
    conn.close()
    return data


###################################
# System routes
###################################
# @cache.memoize()
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
    data = query_database("SELECT folder_id FROM files WHERE file_id = %(file_id)s LIMIT 1", {'file_id': file_id})
    logging.info("data: {}".format(data))
    if data is None:
        filename = "static/na.jpg"
        return send_file(filename, mimetype='image/jpeg')
    elif len(data) == 0:
        filename = "static/na.jpg"
        return send_file(filename, mimetype='image/jpeg')
    else:
        try:
            folder_id = data[0]['folder_id']
            max = request.args.get('max')
            if max is not None:
                width = max
            else:
                width = request.args.get('size')
            if width is None:
                filename = "static/mdpp_previews/folder{}/{}.jpg".format(folder_id, file_id)
            else:
                filename = "static/mdpp_previews/folder{}/{}.jpg".format(folder_id, file_id)
                if os.path.isfile(filename):
                    img = Image.open(filename)
                    wpercent = (int(width) / float(img.size[0]))
                    hsize = int((float(img.size[1]) * float(wpercent)))
                    img = img.resize((int(width), hsize), Image.ANTIALIAS)
                    filename = "/tmp/{}_{}.jpg".format(file_id, width)
                    img.save(filename, icc_profile=img.info.get('icc_profile'))
                else:
                    filename = "static/na.jpg"
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


@cache.memoize()
@app.route('/herbarium_barcode/<int:file_name>/', methods=['GET'], strict_slashes=False)
def get_herbarium(file_name=None):
    """Return image previews from the NMNH Herbarium."""
    if file_name is None:
        raise InvalidUsage('file_name missing', status_code=400)
    #
    query = ("SELECT file_id, folder_id, preview_image FROM files "
             "WHERE file_name = %(file_name)s AND folder_id IN "
             "(SELECT folder_id FROM folders WHERE project_id in(100,131)) LIMIT 1")
    data = query_database(query, {'file_name': file_name})
    logging.info("data: {}".format(data))
    if data is None:
        filename = "static/na.jpg"
        return send_file(filename, mimetype='image/jpeg')
    elif len(data) == 0:
        filename = "static/na.jpg"
        return send_file(filename, mimetype='image/jpeg')
    else:
        data = data[0]
        file_id = data['file_id']
        folder_id = data['folder_id']
        preview_image = data['preview_image']
        logging.info("data: {}".format(data))
        if preview_image is not None:
            redirect(preview_image, code=302)
        else:
            max = request.args.get('max')
            if max is not None:
                width = max
            else:
                width = request.args.get('size')
            if width is None:
                filename = "static/mdpp_previews/folder{}/{}.jpg".format(folder_id, file_id)
                logging.info("245")
            else:
                filename = "static/mdpp_previews/folder{}/{}.jpg".format(folder_id, file_id)
                logging.info("248")
                if os.path.isfile(filename):
                    img = Image.open(filename)
                    wpercent = (int(width) / float(img.size[0]))
                    hsize = int((float(img.size[1]) * float(wpercent)))
                    img = img.resize((int(width), hsize), Image.ANTIALIAS)
                    filename = "/tmp/{}_{}.jpg".format(file_id, width)
                    img.save(filename)
                else:
                    filename = "static/na.jpg"
    if not os.path.isfile(filename):
        logging.info(filename)
        logging.info("259")
        filename = "static/na.jpg"
    #
    logging.info(filename)
    try:
        return send_file(filename, mimetype='image/jpeg')
    except:
        return send_file("static/na.jpg", mimetype='image/jpeg')


#####################################
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
