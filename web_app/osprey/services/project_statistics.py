"""Project summary and detail statistics for the statistics page."""

from __future__ import annotations

import statistics
from datetime import date, datetime

from osprey.db import run_query


def _median(values):
    return float(statistics.median(values))


def _quantile(values, q):
    """Linear interpolation quantile for q in [0, 1]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    weight = pos - low
    return float(ordered[low] * (1 - weight) + ordered[high] * weight)

_STAT_TYPE_TO_CHART = {
    'column': 'bar',
    'area': 'line',
    'boxplot': 'boxplot',
}

_OSPREY_BAR_COLOR = '#3F4249'
_OSPREY_AREA_FILL = 'rgba(63, 66, 73, 0.25)'


def load_summary_stats(project_id):
    """Return (project_stats, project_stats_other) with formatted display strings."""
    row = run_query(
        "SELECT * FROM projects_stats WHERE project_id = %(project_id)s",
        {'project_id': project_id},
    )[0]
    project_stats = {
        'total': format(int(row['images_taken'] or 0), ',d'),
        'ok': format(int(row['project_ok'] or 0), ',d'),
        'errors': format(int(row['project_err'] or 0), ',d'),
        'objects': format(int(row['objects_digitized'] or 0), ',d'),
    }
    project_stats_other = {
        'other_icon': row.get('other_icon'),
        'other_name': row.get('other_name'),
        'other_stat': format(int(row.get('other_stat') or 0), ',d'),
    }
    return project_stats, project_stats_other


def load_detail_stat_cards(proj_id):
    """Return active KPI stat cards (stat_type='stat') ordered by step_order."""
    return run_query(
        (
            "SELECT s.step_info, s.step_notes, s.step_units, s.css, s.round_val, "
            "DATE_FORMAT(s.step_updated_on, '%Y-%m-%d %H:%i:%s') as step_updated_on, "
            "e.step_value "
            "FROM projects_detail_statistics_steps s, projects_detail_statistics e "
            "WHERE s.project_id = %(proj_id)s AND s.stat_type = 'stat' "
            "AND e.step_id = s.step_id AND s.active = 1 "
            "ORDER BY s.step_order"
        ),
        {'proj_id': proj_id},
    )


def load_chart_steps(proj_id):
    """Return active chart steps (column, boxplot, area)."""
    return run_query(
        (
            "SELECT *, DATE_FORMAT(step_updated_on, '%Y-%m-%d %H:%i:%s') as step_updated_on_fmt "
            "FROM projects_detail_statistics_steps "
            "WHERE project_id = %(proj_id)s "
            "AND (stat_type = 'column' OR stat_type = 'boxplot' OR stat_type = 'area') "
            "AND active = 1 "
            "ORDER BY step_order"
        ),
        {'proj_id': proj_id},
    )


def load_chart_rows(step_id):
    """Return date/value/file_name rows for a chart step."""
    return run_query(
        (
            "SELECT date, step_value, file_name "
            "FROM projects_detail_statistics "
            "WHERE step_id = %(step_id)s "
            "ORDER BY date"
        ),
        {'step_id': step_id},
    )


def _format_date(value):
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def normalize_chart_rows(rows, round_val=2):
    """Parse step_value to float; drop invalid rows. Returns list of dicts."""
    try:
        decimals = int(round_val) if round_val is not None else 2
    except (TypeError, ValueError):
        decimals = 2

    normalized = []
    for row in rows or []:
        raw = row.get('step_value')
        if raw is None or raw == '':
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        value = round(value, decimals)
        normalized.append({
            'date': _format_date(row.get('date')),
            'value': value,
            'file_name': row.get('file_name') or '',
        })
    return normalized


def _aggregate_by_date(rows):
    """Sum values by date for column/area charts."""
    totals = {}
    for row in rows:
        key = row['date'] or 'unknown'
        totals[key] = totals.get(key, 0.0) + row['value']
    labels = sorted(totals.keys())
    values = [totals[label] for label in labels]
    return labels, values


def _boxplot_medians(rows):
    """Group by file_name (or date) and return median per group."""
    if not rows:
        return [], [], []

    use_file = any(r.get('file_name') for r in rows)
    groups = {}
    for row in rows:
        key = (row.get('file_name') if use_file else None) or row.get('date') or 'unknown'
        groups.setdefault(key, []).append(row['value'])

    labels = []
    medians = []
    summaries = []
    for key in sorted(groups.keys()):
        vals = groups[key]
        labels.append(str(key))
        medians.append(_median(vals))
        summaries.append({
            'label': str(key),
            'min': float(min(vals)),
            'q1': _quantile(vals, 0.25),
            'median': _median(vals),
            'q3': _quantile(vals, 0.75),
            'max': float(max(vals)),
            'count': len(vals),
        })
    return labels, medians, summaries


def describe_chart(step, rows, labels, values, *, chart_kind='bar', boxplot_summaries=None):
    """Return (short_description, long_description) for accessibility."""
    title = step.get('step_info') or 'Untitled chart'
    units = step.get('step_units') or ''
    notes = (step.get('step_notes') or '').strip()
    kind_label = {
        'bar': 'Bar chart',
        'line': 'Area chart',
        'boxplot': 'Median bar chart from distribution data',
    }.get(chart_kind, 'Chart')

    n = len(values)
    if n == 0:
        short = f"{kind_label}: {title}. No data available."
        long_parts = [short]
        if notes:
            long_parts.append(notes)
        return short, ' '.join(long_parts)

    first_label = labels[0] if labels else ''
    last_label = labels[-1] if labels else ''
    short = (
        f"{kind_label}: {title}. {n} point{'s' if n != 1 else ''}"
        f" from {first_label} to {last_label}."
    )

    total = float(sum(values))
    minimum = float(min(values))
    maximum = float(max(values))
    median = _median(values)
    unit_suffix = f" {units}" if units else ''

    long_parts = [
        short,
        f"Values range from {minimum}{unit_suffix} to {maximum}{unit_suffix}.",
        f"Median is {median}{unit_suffix}; total is {total}{unit_suffix}.",
    ]
    if notes:
        long_parts.append(notes)
    if n >= 2:
        if values[-1] > values[0]:
            long_parts.append("Overall trend is increasing from first to last point.")
        elif values[-1] < values[0]:
            long_parts.append("Overall trend is decreasing from first to last point.")
        else:
            long_parts.append("First and last values are the same.")
    if boxplot_summaries:
        sample = boxplot_summaries[:5]
        parts = [
            (
                f"{s['label']}: min {s['min']}, Q1 {s['q1']}, "
                f"median {s['median']}, Q3 {s['q3']}, max {s['max']} "
                f"(n={s['count']})"
            )
            for s in sample
        ]
        long_parts.append(
            "Distribution summaries (up to five groups): " + '; '.join(parts) + '.'
        )
        if len(boxplot_summaries) > 5:
            long_parts.append(
                f"{len(boxplot_summaries) - 5} additional groups are listed in the data table."
            )
    return short, ' '.join(long_parts)


def build_chart_spec(step, rows, project_title=''):
    """Build chart payload for template/JS, or None when there is no data.

    When rows are empty, returns a dict with ``empty``=True so the template can
    show an info alert instead of a broken image.
    """
    round_val = step.get('round_val', 2)
    normalized = normalize_chart_rows(rows, round_val=round_val)
    step_id = step.get('step_id') or str(step.get('table_id') or '')
    title = step.get('step_info') or 'Untitled chart'
    notes = step.get('step_notes') or ''
    units = step.get('step_units') or ''
    updated_on = step.get('step_updated_on_fmt') or _format_date(step.get('step_updated_on'))
    stat_type = (step.get('stat_type') or 'column').lower()
    chart_type = _STAT_TYPE_TO_CHART.get(stat_type, 'bar')

    base = {
        'step_id': step_id,
        'title': title,
        'notes': notes,
        'units': units,
        'updated_on': updated_on,
        'chart_type': chart_type,
        'project_title': project_title,
        'empty': False,
        'labels': [],
        'datasets': [],
        'table_rows': [],
        'short_description': '',
        'long_description': '',
    }

    if not normalized:
        short, long_desc = describe_chart(step, [], [], [], chart_kind=chart_type)
        base['empty'] = True
        base['short_description'] = short
        base['long_description'] = long_desc
        return base

    boxplot_summaries = None
    if chart_type == 'boxplot':
        labels, values, boxplot_summaries = _boxplot_medians(normalized)
        dataset_label = f"{title} (median)"
        chart_js_type = 'bar'
        fill = False
        table_rows = [
            {
                'date': s['label'],
                'value': s['median'],
                'file_name': '',
                'min': s['min'],
                'q1': s['q1'],
                'median': s['median'],
                'q3': s['q3'],
                'max': s['max'],
                'count': s['count'],
            }
            for s in boxplot_summaries
        ]
        table_mode = 'boxplot'
    else:
        labels, values = _aggregate_by_date(normalized)
        dataset_label = title
        chart_js_type = chart_type  # bar or line
        fill = chart_type == 'line'
        table_rows = [
            {'date': r['date'], 'value': r['value'], 'file_name': r['file_name']}
            for r in normalized
        ]
        table_mode = 'series'

    short, long_desc = describe_chart(
        step, normalized, labels, values,
        chart_kind=chart_type,
        boxplot_summaries=boxplot_summaries,
    )
    if project_title:
        short = short.replace(f"{title}.", f"{title} for {project_title}.", 1)

    dataset = {
        'label': dataset_label,
        'data': values,
        'backgroundColor': _OSPREY_AREA_FILL if fill else _OSPREY_BAR_COLOR,
        'borderColor': _OSPREY_BAR_COLOR,
        'borderWidth': 1,
        'fill': fill,
        'tension': 0.2 if fill else 0,
    }

    base.update({
        'chart_js_type': chart_js_type,
        'labels': labels,
        'datasets': [dataset],
        'table_rows': table_rows,
        'table_mode': table_mode,
        'short_description': short,
        'long_description': long_desc,
        'units': units,
    })
    return base


def build_chart_figures(proj_id, project_title=''):
    """Return list of chart figure dicts for active chart steps."""
    figures = []
    for step in load_chart_steps(proj_id):
        rows = load_chart_rows(step.get('step_id'))
        figures.append(build_chart_spec(step, rows, project_title=project_title))
    return figures


def get_project_row(project_alias):
    """Return project row or None."""
    rows = run_query(
        "SELECT * FROM projects WHERE project_alias = %(project_alias)s",
        {'project_alias': project_alias},
    )
    return rows[0] if rows else None


def load_statistics_page_context(project_alias):
    """Assemble template context for the statistics page.

    Returns a dict with ``found``=False when the project does not exist.
    """
    project_info = get_project_row(project_alias)
    if project_info is None:
        return {'found': False, 'project_alias': project_alias}

    project_id = project_info['project_id']
    proj_id = project_info['proj_id']
    project_stats, project_stats_other = load_summary_stats(project_id)
    detail_cards = load_detail_stat_cards(proj_id)
    # Keep template compatibility with the existing two-row layout.
    proj_stats_vals1 = detail_cards[:3]
    proj_stats_vals2 = detail_cards[3:6]
    chart_figures = build_chart_figures(
        proj_id, project_title=project_info.get('project_title') or '',
    )

    return {
        'found': True,
        'project_alias': project_alias,
        'project_info': project_info,
        'project_stats': project_stats,
        'project_stats_other': project_stats_other,
        'proj_stats_vals1': proj_stats_vals1,
        'proj_stats_vals2': proj_stats_vals2,
        'detail_stat_cards': detail_cards,
        'chart_figures': chart_figures,
    }
