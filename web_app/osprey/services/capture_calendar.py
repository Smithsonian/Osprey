"""Capture calendar: images captured per day, laid out as weeks by weekdays."""

from __future__ import annotations

from datetime import date, timedelta

from osprey.db import run_query
from osprey.services.chart_helpers import heat_level, iso_day, titled
from osprey.services.daily_throughput import load_daily_throughput_rows

WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
WEEKS_SHOWN = 52


def load_holidays(first_day, last_day):
    """Set of ISO dates flagged as holidays in dates_table."""
    rows = run_query(
        'SELECT date FROM dates_table WHERE holiday = 1 AND date BETWEEN %(first)s AND %(last)s',
        {'first': first_day, 'last': last_day},
    )
    return {iso_day(row['date']) for row in rows or []}


def _daily_counts(rows):
    counts = {}
    for row in rows or []:
        day = iso_day(row.get('day'))
        if day:
            counts[day] = int(row.get('images') or 0)
    return counts


def build_capture_calendar_spec(rows, holidays=(), *, project_title=''):
    """Grid of the last 52 weeks with captures (rows = weeks, columns = weekdays)."""
    counts = _daily_counts(rows)
    holidays = set(holidays or ())
    title = titled('Capture calendar', project_title)

    table_columns = [
        {'key': 'date', 'label': 'Date'},
        {'key': 'weekday', 'label': 'Weekday'},
        {'key': 'images', 'label': 'Images'},
        {'key': 'holiday', 'label': 'Holiday'},
    ]
    if not counts:
        short = f'Calendar grid: {title}. No capture dates recorded yet.'
        return {
            'title': title, 'empty': True, 'labels': [], 'datasets': [], 'grids': [],
            'table_rows': [], 'table_columns': table_columns,
            'short_description': short, 'long_description': short,
        }

    last_day = date.fromisoformat(max(counts))
    first_day = date.fromisoformat(min(counts))
    last_monday = last_day - timedelta(days=last_day.weekday())
    first_monday = max(first_day - timedelta(days=first_day.weekday()),
                       last_monday - timedelta(weeks=WEEKS_SHOWN - 1))

    shown = {day: n for day, n in counts.items() if day >= first_monday.isoformat()}
    top = max(shown.values())

    grid_rows = []
    monday = first_monday
    while monday <= last_monday:
        cells = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            iso = day.isoformat()
            images = counts.get(iso, 0)
            holiday = iso in holidays
            text = str(images) if images else ('H' if holiday else '')
            cells.append({
                'text': text,
                'level': heat_level(images, top),
                'title': f'{iso}: {images} image(s)' + (' (holiday)' if holiday else ''),
            })
        grid_rows.append({'label': monday.isoformat(), 'cells': cells})
        monday += timedelta(weeks=1)

    table_rows = [
        {
            'date': day,
            'weekday': WEEKDAYS[date.fromisoformat(day).weekday()],
            'images': images,
            'holiday': 'Yes' if day in holidays else '',
        }
        for day, images in sorted(counts.items())
    ]

    weekdays_idle = sum(
        1 for row in grid_rows for offset, cell in enumerate(row['cells'][:5])
        if cell['level'] == 0 and cell['text'] != 'H'
        and first_day <= date.fromisoformat(row['label']) + timedelta(days=offset) <= last_day
    )
    short = (f'Calendar grid: {title}. {len(shown)} day(s) with captures in the {len(grid_rows)} week(s) '
             f'up to {last_day.isoformat()}; busiest day had {top} image(s); '
             f'{weekdays_idle} weekday(s) with none.')

    return {
        'title': title,
        'empty': False,
        'labels': [],
        'datasets': [],
        'grids': [{
            'title': f'Images captured per day, weeks starting {first_monday.isoformat()} to {last_monday.isoformat()}',
            'row_header': 'Week of',
            'columns': WEEKDAYS,
            'rows': grid_rows,
        }],
        'table_rows': table_rows,
        'table_columns': table_columns,
        'note': ('Darker cells had more images. H marks a holiday with no captures. '
                 'The grid shows the most recent 52 weeks; the CSV has every day.'),
        'short_description': short,
        'long_description': short,
    }


def load_chart(project_id, *, project_title=''):
    rows = load_daily_throughput_rows(project_id)
    days = sorted(_daily_counts(rows))
    holidays = load_holidays(days[0], days[-1]) if days else set()
    return build_capture_calendar_spec(rows, holidays, project_title=project_title)
