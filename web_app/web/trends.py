"""Program-wide views: public trends page and the logged-in project portfolio."""

from datetime import date

from flask import Blueprint
from flask import render_template
from flask import request
from flask_login import current_user
from flask_login import login_required

import settings
from cache import cache
from osprey.services import builtin_reports as builtin_report_service
from osprey.services import program_trends
from web.errors import render_error
from web.forms import LoginForm
from web.reports import chart_csv_response

trends_bp = Blueprint('trends', __name__)

# The series scans every project's counts, and the homepage needs it on each
# request for the sparklines; the numbers behind it change at most daily.
SERIES_CACHE_SECONDS = 6 * 3600
PAGE_CACHE_SECONDS = 3600


@cache.memoize(timeout=SERIES_CACHE_SECONDS)
def monthly_series():
    return program_trends.load_monthly_series()


@cache.memoize(timeout=PAGE_CACHE_SECONDS)
def _unit_rows():
    return program_trends.load_unit_rows()


@cache.memoize(timeout=PAGE_CACHE_SECONDS)
def _timeline_rows():
    return program_trends.load_timeline_rows()


def _charts():
    return {
        'growth': builtin_report_service.finish_chart_spec(
            program_trends.build_growth_chart_spec(monthly_series()), 'growth'),
        'units': builtin_report_service.finish_chart_spec(
            program_trends.build_units_chart_spec(_unit_rows()), 'units'),
    }


@trends_bp.route('/trends/', methods=['GET'], provide_automatic_options=False)
def program_trends_page():
    """Public page: program growth, totals by unit and the project timeline."""
    charts = _charts()
    return render_template(
        'trends.html',
        growth=charts['growth'],
        units=charts['units'],
        project_timeline=program_trends.build_timeline(_timeline_rows(), date.today()),
        form=LoginForm(request.form),
        username=current_user.name if current_user.is_authenticated else None,
        asklogin=settings.site_net == "internal",
    )


@trends_bp.route('/trends/<chart_id>.csv', methods=['GET'], provide_automatic_options=False)
def trends_csv(chart_id=None):
    """Download the data behind one of the trends charts."""
    chart = _charts().get(chart_id)
    if chart is None:
        return render_error("File was not found.", 404)
    return chart_csv_response(chart, f'program-{chart_id}.csv')


@trends_bp.route('/portfolio/', methods=['GET'], provide_automatic_options=False)
@login_required
def portfolio():
    """Logged-in page: every project on one timeline, with progress, by unit or by manager."""
    group_by = 'pm' if request.args.get('group') == 'pm' else 'unit'
    return render_template(
        'portfolio.html',
        project_timeline=program_trends.build_timeline(_timeline_rows(), date.today(), group_by=group_by),
        group_by=group_by,
        form=LoginForm(request.form),
        username=current_user.name,
    )
