"""Program-wide views: growth over time, totals by unit, project timeline, activity sparklines."""

from __future__ import annotations

from datetime import date
from html import escape

from osprey.db import run_query
from osprey.services.chart_helpers import BLUE, VERMILLION, dataset, percent

# projects_stats_detail.time_interval prefixes, finest first. Every interval is
# rolled up to months, so the finest one available loses nothing.
_INTERVAL_PREFIXES = ('da', 'week', 'month', 'year')

SOURCE_STATS = 'stats_detail'
SOURCE_FILES = 'files'


def pick_interval(names):
    """The finest time_interval value among those stored, or None if none is recognised."""
    for prefix in _INTERVAL_PREFIXES:
        for name in names:
            if name and str(name).strip().lower().startswith(prefix):
                return name
    return None


def _month_rows(rows, with_objects):
    out = []
    for row in rows or []:
        if row.get('y') is None or row.get('m') is None:
            continue
        out.append({
            'project_id': row['project_id'],
            'month': '{:04d}-{:02d}'.format(int(row['y']), int(row['m'])),
            'images': int(row.get('images') or 0),
            'objects': int(row.get('objects') or 0) if with_objects else None,
        })
    return out


def load_monthly_series():
    """Images (and objects, when known) per project per month.

    Uses the projects_stats_detail time series when it has rows in a
    recognised interval, where each row is taken to hold the counts for its
    own interval (not a running total). Otherwise falls back to counting
    files by capture date, which has no object counts and only covers
    projects whose files are tracked here.

    Returns {'source', 'rows': [{project_id, month 'YYYY-MM', images, objects}]}.
    """
    intervals = run_query('SELECT DISTINCT time_interval FROM projects_stats_detail')
    interval = pick_interval([row['time_interval'] for row in intervals or []])
    if interval is not None:
        rows = run_query(
            'SELECT d.project_id, YEAR(d.stat_date) AS y, MONTH(d.stat_date) AS m, '
            '  SUM(d.images_captured) AS images, SUM(d.objects_digitized) AS objects '
            'FROM projects_stats_detail d '
            'JOIN projects p ON p.project_id = d.project_id '
            'WHERE d.time_interval = %(interval)s AND d.stat_date IS NOT NULL AND p.skip_project = 0 '
            'GROUP BY d.project_id, y, m',
            {'interval': interval},
        )
        months = _month_rows(rows, with_objects=True)
        if months:
            return {'source': SOURCE_STATS, 'rows': months}

    rows = run_query(
        'SELECT fol.project_id, YEAR(f.datetime_created) AS y, MONTH(f.datetime_created) AS m, '
        '  COUNT(*) AS images '
        'FROM files f '
        'JOIN folders fol ON fol.folder_id = f.folder_id '
        'JOIN projects p ON p.project_id = fol.project_id '
        'WHERE f.datetime_created IS NOT NULL AND p.skip_project = 0 '
        'GROUP BY fol.project_id, y, m'
    )
    return {'source': SOURCE_FILES, 'rows': _month_rows(rows, with_objects=False)}


# ---- S1: program growth ---------------------------------------------------

def build_growth_chart_spec(series):
    """Cumulative images (and objects) across all projects, month by month."""
    rows = (series or {}).get('rows') or []
    has_objects = (series or {}).get('source') == SOURCE_STATS
    per_month = {}
    for row in rows:
        month = per_month.setdefault(row['month'], [0, 0])
        month[0] += row['images']
        month[1] += row['objects'] or 0

    months = sorted(per_month)
    images, objects, table_rows = [], [], []
    total_images = total_objects = 0
    for month in months:
        total_images += per_month[month][0]
        total_objects += per_month[month][1]
        day = month + '-01'
        images.append({'x': day, 'y': total_images})
        objects.append({'x': day, 'y': total_objects})
        row = {'month': month, 'images': per_month[month][0], 'images_total': total_images}
        if has_objects:
            row.update(objects=per_month[month][1], objects_total=total_objects)
        table_rows.append(row)

    line = {'fill': False, 'tension': 0, 'pointRadius': 0, 'borderWidth': 2}
    datasets = [dataset('Images captured', images, BLUE, **line)]
    columns = [
        {'key': 'month', 'label': 'Month'},
        {'key': 'images', 'label': 'Images that month'},
        {'key': 'images_total', 'label': 'Images to date'},
    ]
    if has_objects:
        datasets.append(dataset('Objects digitized', objects, VERMILLION, **line))
        columns += [
            {'key': 'objects', 'label': 'Objects that month'},
            {'key': 'objects_total', 'label': 'Objects to date'},
        ]

    title = 'Program growth'
    empty = not months
    if empty:
        short = f'Line chart: {title}. No dated counts are available.'
    else:
        short = (f'Line chart: {title}. Cumulative totals from {months[0]} to {months[-1]}, '
                 f'reaching {total_images:,} images'
                 + (f' and {total_objects:,} objects.' if has_objects else '.'))

    if has_objects:
        note = 'Running totals of the monthly counts recorded for each project.'
    else:
        note = ('Counted from the capture dates of the image files tracked in this system, so projects '
                'whose files are not tracked here are missing and the line is lower than the program totals.')

    return {
        'title': title,
        'chart_type': 'line',
        'chart_js_type': 'line',
        'x_scale': 'time',
        'time_unit': 'year',
        'units': 'count',
        'empty': empty,
        'labels': months,
        'datasets': datasets,
        'table_rows': table_rows,
        'table_columns': columns,
        'note': note,
        'short_description': short,
        'long_description': short,
    }


# ---- S2: totals by unit ---------------------------------------------------

def load_unit_rows():
    """Objects, images and project counts per museum unit, largest first."""
    return run_query(
        'SELECT p.project_unit AS unit, MAX(u.unit_fullname) AS unit_fullname, '
        '  COUNT(*) AS projects, '
        '  COALESCE(SUM(ps.objects_digitized), 0) AS objects, '
        '  COALESCE(SUM(ps.images_taken), 0) AS images '
        'FROM projects p '
        'LEFT JOIN projects_stats ps ON ps.project_id = p.project_id '
        'LEFT JOIN si_units u ON u.unit_id = p.project_unit '
        'WHERE p.skip_project = 0 '
        'GROUP BY p.project_unit '
        'ORDER BY objects DESC, images DESC, p.project_unit'
    )


def build_units_chart_spec(rows):
    """Horizontal bars per unit: objects digitized and images captured."""
    table_rows = [
        {
            'unit': row.get('unit') or 'Unknown',
            'unit_fullname': row.get('unit_fullname') or '',
            'projects': int(row.get('projects') or 0),
            'objects': int(row.get('objects') or 0),
            'images': int(row.get('images') or 0),
        }
        for row in rows or []
    ]
    title = 'Digitization by museum or unit'
    empty = not table_rows
    if empty:
        short = f'Bar chart: {title}. No projects yet.'
    else:
        top = table_rows[0]
        short = (f'Bar chart: {title}. {len(table_rows)} unit(s); the most objects are from '
                 f"{top['unit_fullname'] or top['unit']} ({top['objects']:,}).")
    return {
        'title': title,
        'chart_type': 'bar',
        'chart_js_type': 'bar',
        'index_axis': 'y',
        'units': 'count',
        'empty': empty,
        'labels': [row['unit'] for row in table_rows],
        'datasets': [
            dataset('Objects digitized', [row['objects'] for row in table_rows], VERMILLION),
            dataset('Images captured', [row['images'] for row in table_rows], BLUE),
        ],
        'table_rows': table_rows,
        'table_columns': [
            {'key': 'unit', 'label': 'Unit'},
            {'key': 'unit_fullname', 'label': 'Name'},
            {'key': 'projects', 'label': 'Projects'},
            {'key': 'objects', 'label': 'Objects digitized'},
            {'key': 'images', 'label': 'Images captured'},
        ],
        # Rows need room: the template sizes the canvas from this.
        'height_px': max(260, 40 * len(table_rows) + 80),
        'short_description': short,
        'long_description': short,
    }


# ---- S4 / P10: project timeline -------------------------------------------

def load_timeline_rows():
    """Every listed project with its dates, status and progress numbers."""
    return run_query(
        'SELECT p.project_id, p.project_title, p.project_alias, p.project_unit, '
        '  u.unit_fullname, p.project_status, p.project_manager, p.project_start, p.project_end, '
        '  ps.objects_digitized, ps.collex_to_digitize '
        'FROM projects p '
        'LEFT JOIN projects_stats ps ON ps.project_id = p.project_id '
        'LEFT JOIN si_units u ON u.unit_id = p.project_unit '
        'WHERE p.skip_project = 0 AND p.project_start IS NOT NULL '
        'ORDER BY p.project_start, p.project_title'
    )


def _as_date(value):
    if value is None:
        return None
    if hasattr(value, 'date') and callable(value.date):
        return value.date()
    return value


def build_timeline(rows, today, *, group_by='unit'):
    """Lay projects out on a shared time axis, grouped by unit or by project manager.

    Returns {'empty', 'start', 'end', 'years': [{label, left}], 'groups':
    [{label, title, rows: [...]}], 'ongoing', 'late'}; left/width are
    percentages of the axis. A project is late when it is still ongoing
    after its planned end date.
    """
    projects = []
    for row in rows or []:
        start = _as_date(row.get('project_start'))
        if start is None:
            continue
        planned_end = _as_date(row.get('project_end'))
        ongoing = str(row.get('project_status') or '').strip().lower() == 'ongoing'
        if ongoing:
            end = max(today, start)
        else:
            end = max(planned_end or start, start)
        goal = int(row.get('collex_to_digitize') or 0)
        done = int(row.get('objects_digitized') or 0)
        projects.append({
            'title': row.get('project_title') or '',
            'alias': row.get('project_alias'),
            'unit': row.get('project_unit') or 'Unknown',
            'unit_fullname': row.get('unit_fullname') or '',
            'manager': row.get('project_manager') or 'Unassigned',
            'status': 'Ongoing' if ongoing else (row.get('project_status') or ''),
            'ongoing': ongoing,
            'late': bool(ongoing and planned_end and planned_end < today),
            'start': start,
            'end': end,
            'dates': '{} to {}'.format(start.isoformat(), 'present' if ongoing else end.isoformat()),
            'planned_end': planned_end.isoformat() if planned_end else '',
            'progress': min(100, percent(done, goal, 0)) if goal else None,
        })

    if not projects:
        return {'empty': True, 'groups': [], 'years': [], 'ongoing': 0, 'late': 0}

    axis_start = date(min(p['start'] for p in projects).year, 1, 1)
    axis_end = date(max(max(p['end'] for p in projects), today).year, 12, 31)
    span = (axis_end - axis_start).days or 1

    def position(day):
        return round((day - axis_start).days / span * 100, 2)

    for project in projects:
        project['left'] = position(project['start'])
        # Keep one-day projects visible.
        project['width'] = max(0.4, round(position(project['end']) - project['left'], 2))

    years = [
        {'label': str(year), 'left': position(date(year, 1, 1))}
        for year in range(axis_start.year, axis_end.year + 1)
    ]
    # Label at most ~12 years so they do not run into each other.
    step = max(1, -(-len(years) // 12))
    for index, year in enumerate(years):
        year['show'] = index % step == 0

    key = 'manager' if group_by == 'pm' else 'unit'
    groups = {}
    for project in projects:
        group = groups.setdefault(project[key], {
            'label': project[key],
            'title': project['unit_fullname'] if key == 'unit' else '',
            'rows': [],
        })
        group['rows'].append(project)

    return {
        'empty': False,
        'start': axis_start.isoformat(),
        'end': axis_end.isoformat(),
        'years': years,
        'groups': [groups[label] for label in sorted(groups)],
        'ongoing': sum(1 for p in projects if p['ongoing']),
        'late': sum(1 for p in projects if p['late']),
        'total': len(projects),
    }


# ---- S6: activity sparklines ----------------------------------------------

def last_months(today, count=12):
    """The last `count` months up to and including today's, oldest first, as 'YYYY-MM'."""
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append('{:04d}-{:02d}'.format(year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months[::-1]


def recent_activity(series, today, count=12):
    """{project_id: [images per month for the last `count` months]} for projects with any."""
    months = last_months(today, count)
    index = {month: i for i, month in enumerate(months)}
    activity = {}
    for row in (series or {}).get('rows') or []:
        i = index.get(row['month'])
        if i is None or not row['images']:
            continue
        activity.setdefault(row['project_id'], [0] * count)[i] += row['images']
    return activity


def sparkline_svg(values, months):
    """Inline SVG bar sparkline with a text alternative; '' when there is nothing to show."""
    if not values or not max(values):
        return ''
    top = max(values)
    peak = months[values.index(top)]
    label = ('Images per month, {} to {}: {:,} in total, most in {} ({:,}).'
             .format(months[0], months[-1], sum(values), peak, top))
    bar_width, gap, height = 5, 1, 20
    bars = []
    for i, value in enumerate(values):
        bar_height = round(value / top * height, 1) if value else 0
        if value and bar_height < 1:
            bar_height = 1
        bars.append('<rect x="{x}" y="{y}" width="{w}" height="{h}"/>'.format(
            x=i * (bar_width + gap), y=round(height - bar_height, 1), w=bar_width, h=bar_height))
    width = len(values) * (bar_width + gap) - gap
    return ('<svg class="homepage-sparkline" role="img" aria-label="{label}" '
            'viewBox="0 0 {w} {h}" width="{w}" height="{h}" fill="{fill}">'
            '<title>{label}</title>{bars}</svg>').format(
                label=escape(label, quote=True), w=width, h=height, fill=BLUE, bars=''.join(bars))
