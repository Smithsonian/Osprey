"""API Blueprint package."""

from flask import Blueprint

api_bp = Blueprint('api', __name__)

from api import errors  # noqa: E402, F401
from api.routes import discovery, projects, folders, files, reports, worker  # noqa: E402, F401
