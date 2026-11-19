"""Small helpers shared by the built-in chart reports."""

from __future__ import annotations

import statistics
from datetime import date, datetime

# Okabe-Ito colors (colorblind-safe), minus the yellow, which is too faint on white.
PALETTE = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9', '#000000']
BLUE, VERMILLION, GREEN = PALETTE[0], PALETTE[1], PALETTE[2]


def color_at(index):
    return PALETTE[index % len(PALETTE)]


def iso_day(value):
    """ISO YYYY-MM-DD for a date, datetime or date-like string ('' when missing)."""
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if text else ''


def titled(title, project_title=''):
    return f'{title} for {project_title}' if project_title else title


def dataset(label, data, color, **extra):
    """A Chart.js dataset in one solid color."""
    row = {
        'label': label,
        'data': data,
        'backgroundColor': color,
        'borderColor': color,
        'borderWidth': 1,
    }
    row.update(extra)
    return row


def percent(part, whole, digits=1):
    """part / whole as a percentage; 0 when there is nothing to divide by."""
    if not whole:
        return 0
    return round(float(part) / float(whole) * 100, digits)


def five_numbers(values, digits=1):
    """min, Q1, median, Q3, max of a list of numbers (None when the list is empty)."""
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        q1 = q3 = values[0]
    else:
        q1, _, q3 = statistics.quantiles(values, n=4, method='inclusive')
    return {
        'n': len(values),
        'min': round(values[0], digits),
        'q1': round(q1, digits),
        'median': round(statistics.median(values), digits),
        'q3': round(q3, digits),
        'max': round(values[-1], digits),
    }


def heat_level(value, top):
    """0-4 intensity of value on a 0..top scale (0 only for zero or missing values)."""
    if not value or not top:
        return 0
    return min(4, 1 + int(float(value) / float(top) * 4 * 0.999))
