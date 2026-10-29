"""partials/_qc_method_badge.html: the active QC method on the /qc/ pages."""

import pytest

from app import app

SETTINGS = {'qc_threshold_critical': 0, 'qc_threshold_major': 1.5, 'qc_threshold_minor': 4,
            'w_major': 1, 'w_minor': 0.3, 'weighted_rate': 6}


def _render(project_settings):
    with app.test_request_context():
        return app.jinja_env.get_template('partials/_qc_method_badge.html').render(
            project_settings=project_settings)


@pytest.mark.parametrize('method', [None, 'weighted'])
def test_weighted_badge(method):
    html = _render(dict(SETTINGS, qc_method=method))
    assert '>Weighted</span>' in html
    assert 'weighted_rate' not in html and '&le; 6%' in html


def test_cumulative_badge():
    html = _render(dict(SETTINGS, qc_method='cumulative'))
    assert '>Cumulative</span>' in html
    assert 'critical + major &le; 1.5%' in html and 'all issues &le; 4%' in html
