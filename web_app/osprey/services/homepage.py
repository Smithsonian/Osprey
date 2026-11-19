"""Numbers and project rows for the public homepage (app.py `homepage`).

Everything here returns plain values; the HTML (links, progress bars,
abbreviations) is built in templates/home.html, where it is escaped.
"""

from __future__ import annotations

from osprey.db import run_query

# URL team -> projects.project_section; 'summary' covers every section.
SECTIONS = {'summary': None, 'md': 'MD', 'is': 'IS'}


def load_section_stats(section=None):
    """Totals for the stat cards, for one section or (None) all of them."""
    where = 'WHERE p.skip_project IS NOT True'
    params = {}
    if section:
        where += ' AND p.project_section = %(section)s'
        params['section'] = section
    row = run_query(
        'SELECT COUNT(*) AS projects, '
        "  COALESCE(SUM(p.project_status = 'Ongoing'), 0) AS active, "
        '  COALESCE(SUM(ps.objects_digitized), 0) AS objects, '
        '  COALESCE(SUM(ps.images_taken), 0) AS images, '
        '  COALESCE(SUM(ps.images_public), 0) AS images_public '
        'FROM projects p LEFT JOIN projects_stats ps ON ps.project_id = p.project_id '
        + where,
        params,
    )[0]
    # MySQL SUM() returns Decimal
    return {key: int(value or 0) for key, value in row.items()}


def load_informatics_stats():
    row = run_query(
        'SELECT COUNT(*) AS projects, '
        "  COALESCE(SUM(project_status = 'Ongoing'), 0) AS active, "
        '  COALESCE(SUM(CASE WHEN records_redundant IS False THEN records ELSE 0 END), 0) AS records '
        'FROM projects_informatics'
    )[0]
    return {key: int(value or 0) for key, value in row.items()}


def load_last_update():
    rows = run_query("SELECT date_format(MAX(updated_at), '%d-%b-%Y') AS updated_at FROM projects_stats")
    return (rows[0]['updated_at'] if rows else None) or 'unknown'


def load_section_projects(section, unit=None):
    """Listed projects of one section (optionally one unit), in homepage order."""
    query = (
        'SELECT p.project_id, p.project_title, p.project_alias, p.project_unit, u.unit_fullname, '
        '  p.project_status, p.project_manager, p.project_start, p.project_end, '
        '  p.objects_estimated, p.images_estimated, '
        '  ps.collex_to_digitize, ps.objects_digitized, ps.images_taken, ps.images_public '
        'FROM projects p '
        'LEFT JOIN projects_stats ps ON ps.project_id = p.project_id '
        'LEFT JOIN si_units u ON u.unit_id = p.project_unit '
        'WHERE p.skip_project = 0 AND p.project_section = %(section)s '
    )
    params = {'section': section}
    if unit:
        query += 'AND p.project_unit = %(unit)s '
        params['unit'] = unit
    return run_query(query + 'ORDER BY p.projects_order DESC', params)


def format_project_dates(start, end):
    """'03 Jan 2024 -', '03 - 21 Jan 2024', '03 Jan - 21 Mar 2024' or both dates in full."""
    if start is None:
        return ''
    full = '%d %b %Y'
    if end is None:
        return f'{start:{full}} -'
    if start == end:
        return f'{start:{full}}'
    if (start.year, start.month) == (end.year, end.month):
        return f'{start:%d} - {end:{full}}'
    if start.year == end.year:
        return f'{start:%d %b} - {end:{full}}'
    return f'{start:{full}} - {end:{full}}'


def _count(value, estimated):
    """(text, number): '12,345' or '12,345*' when the value was estimated."""
    number = int(value or 0)
    return '{:,}{}'.format(number, '*' if estimated else ''), number


def project_table_rows(rows, sparklines=None):
    """Rows for the homepage project tables.

    sparklines maps project_id to ready-made SVG markup (see
    program_trends.sparkline_svg); projects without one get ''.
    """
    sparklines = sparklines or {}
    out = []
    for row in rows or []:
        goal = int(row.get('collex_to_digitize') or 0)
        done = int(row.get('objects_digitized') or 0)
        progress = None
        if row.get('project_alias') and row.get('project_status') == 'Ongoing' and goal:
            # Half-up, as MySQL ROUND() did when this was built in SQL.
            progress = int(done / goal * 100 + 0.5)
        objects_text, objects = _count(row.get('objects_digitized'), row.get('objects_estimated'))
        images_text, images = _count(row.get('images_taken'), row.get('images_estimated'))
        public_text, public = _count(row.get('images_public'), row.get('images_estimated'))
        out.append({
            'title': row.get('project_title') or '',
            'alias': row.get('project_alias'),
            'unit': row.get('project_unit') or '',
            'unit_fullname': row.get('unit_fullname') or '',
            'status': row.get('project_status') or '',
            'manager': row.get('project_manager') or '',
            'dates': format_project_dates(row.get('project_start'), row.get('project_end')),
            'start': row['project_start'].isoformat() if row.get('project_start') else '',
            'progress': progress,
            # The bar can only be full; the text still says e.g. 104 %.
            'progress_bar': min(progress, 100) if progress is not None else None,
            'objects': objects, 'objects_text': objects_text,
            'images': images, 'images_text': images_text,
            'images_public': public, 'images_public_text': public_text,
            'sparkline': sparklines.get(row.get('project_id'), ''),
        })
    return out


def public_share(images_public, images):
    """Whole-number percentage of captured images that are public (None when nothing was captured)."""
    if not images:
        return None
    return int(images_public / images * 100 + 0.5)



def with_descriptions(featured):
    """Featured project cards with each project's project_description as 'description'.

    Cards that link to a dashboard look the description up by project_alias;
    a missing project or an empty description gives ''.
    """
    aliases = [item['project_alias'] for item in featured if item.get('project_alias')]
    descriptions = {}
    if aliases:
        rows = run_query(
            'SELECT project_alias, project_description FROM projects WHERE project_alias IN ({})'.format(
                ', '.join(['%(a{})s'.format(i) for i in range(len(aliases))])),
            {'a{}'.format(i): alias for i, alias in enumerate(aliases)},
        )
        descriptions = {row['project_alias']: (row.get('project_description') or '').strip() for row in rows or []}
    return [dict(item, description=descriptions.get(item.get('project_alias'), '')) for item in featured]
