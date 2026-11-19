"""Homepage: stat queries, project table rows, this-year counts, caching and escaping."""

from datetime import date
from unittest.mock import patch

import pytest

from osprey.services import homepage as hp


# ---- services ---------------------------------------------------------------

def test_section_stats_is_one_query_filtered_by_section():
    with patch.object(hp, 'run_query', return_value=[
            {'projects': 3, 'active': 2, 'objects': 10, 'images': 40, 'images_public': None}]) as rq:
        assert hp.load_section_stats('MD') == {
            'projects': 3, 'active': 2, 'objects': 10, 'images': 40, 'images_public': 0}
        query, params = rq.call_args.args
        assert 'project_section = %(section)s' in query and params == {'section': 'MD'}
        hp.load_section_stats(None)
        query, params = rq.call_args.args
        assert 'project_section' not in query and params == {}


@pytest.mark.parametrize('start, end, text', [
    (date(2024, 1, 3), None, '03 Jan 2024 -'),
    (date(2024, 1, 3), date(2024, 1, 3), '03 Jan 2024'),
    (date(2024, 1, 3), date(2024, 1, 21), '03 - 21 Jan 2024'),
    (date(2024, 1, 3), date(2024, 3, 21), '03 Jan - 21 Mar 2024'),
    (date(2023, 1, 3), date(2024, 3, 21), '03 Jan 2023 - 21 Mar 2024'),
    (None, None, ''),
])
def test_project_dates_match_the_old_sql_formatting(start, end, text):
    assert hp.format_project_dates(start, end) == text


def _project(**overrides):
    row = {'project_id': 1, 'project_title': 'Bees', 'project_alias': 'bees', 'project_unit': 'NMNH',
           'unit_fullname': 'Natural History', 'project_status': 'Ongoing', 'project_manager': 'Ana',
           'project_start': date(2024, 1, 3), 'project_end': None, 'objects_estimated': 0,
           'images_estimated': 1, 'collex_to_digitize': 200, 'objects_digitized': 1234567,
           'images_taken': 50, 'images_public': None}
    row.update(overrides)
    return row


def test_project_rows_progress_numbers_and_estimates():
    row, = hp.project_table_rows([_project(objects_digitized=105, collex_to_digitize=200)], {1: '<svg/>'})
    assert (row['progress'], row['progress_bar']) == (53, 53)          # 52.5 rounds half-up
    assert (row['objects'], row['objects_text']) == (105, '105')
    assert row['images_text'] == '50*' and row['images_public_text'] == '0*'
    assert row['dates'] == '03 Jan 2024 -' and row['start'] == '2024-01-03'
    assert row['sparkline'] == '<svg/>'


def test_project_rows_progress_only_for_ongoing_linked_projects_with_a_goal():
    over, = hp.project_table_rows([_project(objects_digitized=260, collex_to_digitize=200)])
    assert (over['progress'], over['progress_bar']) == (130, 100)
    for overrides in ({'project_status': 'Completed'}, {'project_alias': None}, {'collex_to_digitize': 0}):
        row, = hp.project_table_rows([_project(**overrides)])
        assert row['progress'] is None
    assert hp.project_table_rows([_project()])[0]['sparkline'] == ''


def test_featured_projects_take_their_text_from_the_database():
    featured = [{'title': 'A', 'project_alias': 'a'}, {'title': 'B', 'project_alias': 'b'}, {'title': 'C'}]
    with patch.object(hp, 'run_query', return_value=[
            {'project_alias': 'a', 'project_description': '  Bees and more. '}]) as rq:
        cards = hp.with_descriptions(featured)
    query, params = rq.call_args.args
    assert 'IN (%(a0)s, %(a1)s)' in query and params == {'a0': 'a', 'a1': 'b'}
    assert [c['description'] for c in cards] == ['Bees and more.', '', '']
    assert 'description' not in featured[0]


def test_public_share():
    assert hp.public_share(41, 100) == 41
    assert hp.public_share(5, 0) is None


# ---- route ------------------------------------------------------------------

pytest.importorskip('flask')
pytest.importorskip('flask_login')
pytest.importorskip('flask_wtf')
pytest.importorskip('pandas')

from app import app  # noqa: E402
from cache import cache  # noqa: E402
from osprey.services import program_trends as pt  # noqa: E402
from osprey.services import yearly_stats as ys  # noqa: E402

_STATS = {'projects': 4, 'active': 2, 'objects': 2_345_678, 'images': 1000, 'images_public': 410}


def _fake_db(projects):
    calls = []

    def rq(query, params=None):
        calls.append(query)
        if 'COUNT(*) AS projects' in query:
            return [dict(_STATS)]
        if 'MAX(updated_at)' in query:
            return [{'updated_at': '01-Nov-2026'}]
        if 'projects_order' in query:
            return projects
        if 'project_description' in query:
            return [{'project_alias': 'jpc_production', 'project_description': 'From the <database>.'}]
        raise AssertionError('unexpected query: ' + query)
    return rq, calls


@pytest.fixture()
def client(monkeypatch):
    app.config['TESTING'] = True
    monkeypatch.setattr(app, 'secret_key', 'test-only-not-a-secret')
    # No yearly counts unless a test says otherwise.
    monkeypatch.setattr(ys, 'load_year_totals', lambda section, year: None)
    cache.clear()
    yield app.test_client()
    cache.clear()


_SERIES = {'source': 'stats_detail', 'rows': [
    {'project_id': 1, 'month': '{:%Y}-01'.format(date.today()), 'images': 300, 'objects': 120}]}


def test_summary_tab_shows_year_lines_and_public_share_without_listing_projects(client, monkeypatch):
    year = date.today().year
    asked = []
    monkeypatch.setattr(ys, 'load_year_totals',
                        lambda section, y: asked.append((section, y)) or {'objects': 120, 'images': 300, 'year': y})
    rq, calls = _fake_db([])
    with patch.object(hp, 'run_query', side_effect=rq), patch.object(pt, 'load_monthly_series', return_value=_SERIES):
        html = client.get('/').get_data(as_text=True)
    assert '2,345,678' in html and '41% of images captured' in html
    assert '+300 in {}'.format(year) in html and '+120 in {}'.format(year) in html
    assert asked == [(None, year)]
    assert not any('projects_order' in q for q in calls)
    # Featured card text comes from projects.project_description, escaped.
    assert 'From the &lt;database&gt;.' in html
    assert 'Production 1A' not in html


def test_md_tab_builds_an_escaped_table_and_is_cached(client):
    projects = [_project(project_title='<b>Bees & wasps</b>', objects_digitized=50, collex_to_digitize=100)]
    rq, calls = _fake_db(projects)
    with patch.object(hp, 'run_query', side_effect=rq), patch.object(pt, 'load_monthly_series', return_value=_SERIES):
        first = client.get('/team/md')
        queries = len(calls)
        second = client.get('/team/md')
    html = first.get_data(as_text=True)
    assert first.status_code == 200 and second.status_code == 200
    assert '&lt;b&gt;Bees &amp; wasps&lt;/b&gt;' in html and '<b>Bees' not in html
    assert 'href="/dashboard/bees/"' in html and 'Estimated Progress: 50 %' in html
    assert 'data-order="50"' in html and 'homepage-sparkline' in html
    assert 'over 2.3 million items' in html
    assert len(calls) == queries      # second visit served from the cache


def test_is_tab_shows_public_images_and_sawhm_filter(client, monkeypatch):
    def no_table(section, year):
        raise RuntimeError('projects_stats_yearly does not exist')
    monkeypatch.setattr(ys, 'load_year_totals', no_table)
    rq, calls = _fake_db([_project()])
    with patch.object(hp, 'run_query', side_effect=rq) as mock, \
            patch.object(pt, 'load_monthly_series', side_effect=RuntimeError('no table')):
        html = client.get('/team/is/sawhm').get_data(as_text=True)
        project_query = [c for c in mock.call_args_list if 'projects_order' in c.args[0]][0]
    assert 'Images Public' in html and 'SAWHM projects only' in html
    assert project_query.args[1] == {'section': 'IS', 'unit': 'SAWHM'}
    # The series and the history failed: no sparkline column and no year lines, but the page still works.
    assert 'Images per Month' not in html and 'homepage-stat-delta' not in html.split('Images Public</div>')[0]


def test_unknown_team_is_404(client):
    assert client.get('/team/nope').status_code == 404


def test_cached_data_from_older_code_is_not_served(client, monkeypatch):
    """Entries cached under an older HOMEPAGE_DATA_VERSION are ignored."""
    import app as appmod
    rq, calls = _fake_db([])
    with patch.object(hp, 'run_query', side_effect=rq), patch.object(pt, 'load_monthly_series', return_value=_SERIES):
        monkeypatch.setattr(appmod, 'HOMEPAGE_DATA_VERSION', 1)
        client.get('/')
        before = len(calls)
        monkeypatch.setattr(appmod, 'HOMEPAGE_DATA_VERSION', 4)
        html = client.get('/').get_data(as_text=True)
    assert len(calls) > before
    assert 'From the &lt;database&gt;.' in html


def test_md_tab_asks_for_its_section_and_hides_a_zero(client, monkeypatch):
    monkeypatch.setattr(ys, 'load_year_totals', lambda section, y: {'objects': 0, 'images': 75, 'year': y}
                        if section == 'MD' else None)
    rq, _ = _fake_db([])
    with patch.object(hp, 'run_query', side_effect=rq), patch.object(pt, 'load_monthly_series', return_value=_SERIES):
        html = client.get('/team/md').get_data(as_text=True)
    year = date.today().year
    assert '+75 in {}'.format(year) in html and '+0 in' not in html
