"""User permission and visitor checks shared by the dashboard web views."""

from flask_login import current_user

from cache import cache
from osprey.db import run_query


@cache.memoize()
def kiosk_mode(request, kiosks):
    # User IP, for kiosk mode
    request_address = request.remote_addr
    if request_address in kiosks:
        return True, request_address
    else:
        return False, request_address


@cache.memoize()
def user_perms(project_id, user_type='user'):
    try:
        user_name = current_user.name
    except:
        return False
    val = False
    if user_type == 'user':
        query = ("SELECT COUNT(*) as is_user FROM qc_projects p, users u "
                 " WHERE p.user_id = u.user_id AND p.project_id = %(project_id)s AND u.username = %(user_name)s")
        is_user = run_query(query, {'project_id': project_id, 'user_name': user_name})
        val = is_user[0]['is_user'] == 1
    if user_type == 'admin':
        query = ("SELECT COUNT(*) as is_admin FROM users "
                 " WHERE username = %(user_name)s AND is_admin = 1")
        is_admin = run_query(query, {'user_name': user_name})
        val = is_admin[0]['is_admin'] == 1
    return val
