"""Report read API routes."""

from flask import jsonify, request

from api import api_bp
from api.auth import validate_api_key
from logger import api_logger as logger
from osprey.services import reports as report_service


@api_bp.route('/reports/', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
@api_bp.route('/reports/<report_id>/', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_report(report_id=None):
    """Get the data from a project report."""
    logger.info("api_get_report called | report_id={}".format(report_id))
    if report_id is None:
        return jsonify({'error': 'report_id is missing'}), 400
    api_key = request.form.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'api_key is missing'}), 400
    valid_api_key, _is_admin = validate_api_key(
        api_key, url='/reports/', params="report_id={}".format(report_id)
    )
    if valid_api_key is False:
        logger.warning("api_get_report: invalid api_key | report_id={}".format(report_id))
        return jsonify({'error': 'Forbidden'}), 403
    data = report_service.get_report(report_id)
    if len(data) == 0:
        logger.warning("api_get_report: report not found | report_id={}".format(report_id))
        return jsonify({'error': 'Report not found'}), 404
    return jsonify(data)
