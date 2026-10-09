"""System admin page: read-only status for users with users.sysadmin = 1.

Only served on internal deployments (site_net == "internal"). Anyone else
who reaches the URL — wrong site, or not a sysadmin — is sent to /home.
"""

from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import url_for
from flask_login import current_user
from flask_login import login_required

import settings
from logger import logger
from osprey.services import system_status
from osprey.services.permissions import user_perms

sysadmin_bp = Blueprint('sysadmin', __name__, url_prefix='/sysadmin')


def sysadmin_allowed():
    """True only for a sysadmin on an internal deployment.

    The site check runs first so external/api sites never query the flag.
    """
    if settings.site_net != 'internal':
        return False
    return user_perms('', user_type='sysadmin')


@sysadmin_bp.route('/', methods=['GET'], provide_automatic_options=False)
@login_required
def index():
    if not sysadmin_allowed():
        logger.warning("sysadmin page denied for {} (site_net={})".format(
            current_user.name, settings.site_net))
        return redirect(url_for('home'))
    logger.info("sysadmin page viewed by {}".format(current_user.name))
    return render_template('sysadmin.html', username=current_user.name,
                           status=system_status.collect())
