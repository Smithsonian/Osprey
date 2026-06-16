"""API route discovery."""

from flask import current_app, jsonify

from cache import cache

from api import api_bp
from api.config import config


@cache.memoize()
@api_bp.route('/', methods=['GET', 'POST'], strict_slashes=False, provide_automatic_options=False)
def api_route_list():
    """Print available routes in JSON"""
    func_list = {}
    for rule in current_app.url_map.iter_rules():
        if not rule.rule.startswith('/api'):
            continue
        if '/new/' in rule.rule or '/update/' in rule.rule:
            continue
        if rule.rule in ('/api/reports/', '/api/reports/<report_id>/'):
            continue
        func_list[rule.rule] = current_app.view_functions[rule.endpoint].__doc__
    data = {
        'routes': func_list,
        'sys_ver': config.SITE_VER,
        'env': config.SITE_ENV,
        'net': 'api',
    }
    return jsonify(data)
