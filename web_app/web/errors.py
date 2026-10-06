"""Shared error page for the browser-facing views."""

from flask import render_template


def render_error(error_msg, status_code, project_alias=None):
    """Render error.html with an HTTP status code.

    site_env/site_net/site_ver/analytics_code come from the app-wide context
    processor in app.py, so callers only pass what is specific to the error.
    project_alias, when set, makes the page's "Go back" link point to that
    project's dashboard instead of the homepage.
    """
    return render_template('error.html', error_msg=error_msg, project_alias=project_alias), status_code
