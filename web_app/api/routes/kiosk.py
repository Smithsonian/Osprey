"""Kiosk check-in API routes."""

from flask import jsonify, request

from api import api_bp
from api.auth import validate_api_key
from logger import api_logger as logger
from osprey.db import query_database_insert


@api_bp.route('/kiosk', methods=['POST'], strict_slashes=False, provide_automatic_options=False)
def api_kiosk_checkin():
    """Record a kiosk machine check-in (machine_name, ip, timestamp)."""
    api_key = request.form.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'api_key is missing'}), 400

    machine_name = request.form.get("machine_name")
    ip = request.form.get("ip")
    if machine_name is None or machine_name == "":
        return jsonify({'error': 'machine_name is missing'}), 400
    if ip is None or ip == "":
        return jsonify({'error': 'ip is missing'}), 400

    valid_api_key, _is_admin = validate_api_key(
        api_key, url='/api/kiosk', params="machine_name={}".format(machine_name),
    )
    if valid_api_key is False:
        logger.warning("api_kiosk_checkin: invalid api_key | machine_name={}".format(machine_name))
        return jsonify({'error': 'Forbidden'}), 403

    # Append-only log: every check-in is its own row (full history per machine).
    query = (
        "INSERT INTO kiosk (machine_name, ip, reported_at) "
        "VALUES (%(machine_name)s, %(ip)s, CURRENT_TIMESTAMP)"
    )
    query_database_insert(query, {'machine_name': machine_name, 'ip': ip})

    logger.info("api_kiosk_checkin: machine_name={} ip={}".format(machine_name, ip))
    return jsonify({'result': True})
