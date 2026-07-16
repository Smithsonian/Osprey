"""Daily images and objects digitized per project, sourced from files."""

from __future__ import annotations

from datetime import date, datetime

from osprey.db import run_query
from osprey.services.img2obj import get_project_img2obj_sql

# Okabe-Ito colors: colorblind-safe and clearly distinguishable.
_IMAGES_COLOR = '#0072B2'
_OBJECTS_COLOR = '#D55E00'


def _format_day(value):
    """Normalize day values to ISO YYYY-MM-DD for Chart.js time scale."""
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if text else ''


def load_daily_throughput_rows(project_id):
    """Return [{day, images, objects}, ...] ordered by day (from datetime_created)."""
    obj_sql = get_project_img2obj_sql(project_id)
    query = (
        'SELECT '
        '  DATE(f.datetime_created) AS day, '
        '  COUNT(DISTINCT f.file_name) AS images, '
        f'  COUNT(DISTINCT {obj_sql}) AS objects '
        'FROM files f '
        'JOIN folders fol ON fol.folder_id = f.folder_id '
        'WHERE fol.project_id = %(project_id)s '
        '  AND f.datetime_created IS NOT NULL '
        "  AND f.file_name IS NOT NULL AND TRIM(f.file_name) != '' "
        'GROUP BY day '
        'ORDER BY day'
    )
    return run_query(query, {'project_id': project_id})


def build_daily_throughput_chart_spec(rows, *, project_title=''):
    """Build a two-series time-series column chart spec for Chart.js."""
    labels = []
    images = []
    objects = []
    for row in rows or []:
        day = _format_day(row.get('day'))
        if not day:
            continue
        labels.append(day)
        images.append(int(row.get('images') or 0))
        objects.append(int(row.get('objects') or 0))

    title = 'Daily throughput'
    if project_title:
        title = f'{title} for {project_title}'

    empty = not labels
    if empty:
        short = f'Time series bar chart: {title}. No data available.'
    else:
        short = (
            f'Time series bar chart: {title}. {len(labels)} day(s) '
            f'from {labels[0]} to {labels[-1]}.'
        )

    return {
        'title': title,
        'chart_type': 'bar',
        'chart_js_type': 'bar',
        'x_scale': 'time',
        'time_unit': 'day',
        'units': 'count',
        'empty': empty,
        'labels': labels,
        'datasets': [
            {
                'label': 'Images',
                'data': [
                    {'x': day, 'y': value}
                    for day, value in zip(labels, images)
                ],
                'backgroundColor': _IMAGES_COLOR,
                'borderColor': _IMAGES_COLOR,
                'borderWidth': 1,
            },
            {
                'label': 'Objects',
                'data': [
                    {'x': day, 'y': value}
                    for day, value in zip(labels, objects)
                ],
                'backgroundColor': _OBJECTS_COLOR,
                'borderColor': _OBJECTS_COLOR,
                'borderWidth': 1,
            },
        ],
        'table_rows': [
            {'date': label, 'images': img, 'objects': obj}
            for label, img, obj in zip(labels, images, objects)
        ],
        'table_mode': 'throughput',
        'short_description': short,
        'long_description': short,
    }
