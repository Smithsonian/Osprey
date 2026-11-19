#!/usr/bin/env python3
"""Render a small set of templates into static HTML for a11y checks.

This avoids requiring a running server, database, or Flask runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "out"
TEST_TEMPLATES = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DummyRequest:
    endpoint: str | None = None


def url_for(endpoint: str, **values) -> str:
    # Minimal stub for template rendering. This is sufficient for static a11y checks.
    if endpoint == "static":
        filename = values.get("filename", "")
        return f"/static/{filename}"
    return f"/{endpoint}"


def _report_groups(reports):
    # The app registers this filter in app.py; import lazily so rendering
    # still needs no Flask app or database.
    from osprey.services.builtin_reports import group_reports
    return group_reports(reports)


def build_env() -> Environment:
    loader = FileSystemLoader([str(TEST_TEMPLATES), str(ROOT / "templates")])
    env = Environment(
        loader=loader,
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    )
    env.filters["report_groups"] = _report_groups
    env.globals.update(
        url_for=url_for,
        request=DummyRequest(endpoint="a11y_smoke"),
        csrf_token=lambda: "a11y-csrf-token",
    )
    return env


def statistics_context() -> dict:
    """Minimal context for rendering templates/statistics.html for a11y checks."""
    return {
        "site_env": "dev",
        "site_net": "internal",
        "site_ver": "test",
        "analytics_code": "",
        "username": "",
        "asklogin": True,
        "form": None,
        "project_alias": "demo-project",
        "project_info": {
            "project_title": "Demo Digitization Project",
            "obj_type": "Objects",
            "project_message": None,
            "proj_id": "demo-proj",
        },
        "project_stats": {
            "total": "100",
            "ok": "90",
            "errors": "10",
            "objects": "50",
        },
        "project_stats_other": {
            "other_stat": "0",
            "other_name": "",
            "other_icon": "",
        },
        "proj_stats_vals1": [],
        "proj_stats_vals2": [],
        "chart_figures": [
            {
                "step_id": "step-1",
                "title": "Daily files ingested",
                "notes": "Files counted by capture date.",
                "units": "files",
                "updated_on": "2024-06-01 12:00:00",
                "chart_type": "bar",
                "chart_js_type": "bar",
                "empty": False,
                "labels": ["2024-01-01", "2024-01-02"],
                "datasets": [
                    {
                        "label": "Daily files ingested",
                        "data": [2, 5],
                        "backgroundColor": "#3F4249",
                        "borderColor": "#3F4249",
                        "borderWidth": 1,
                        "fill": False,
                    }
                ],
                "short_description": (
                    "Bar chart: Daily files ingested for Demo Digitization Project. "
                    "2 points from 2024-01-01 to 2024-01-02."
                ),
                "long_description": (
                    "Bar chart: Daily files ingested. Values range from 2 files to 5 files. "
                    "Median is 3.5 files; total is 7 files."
                ),
                "table_mode": "series",
                "table_rows": [
                    {"date": "2024-01-01", "value": 2, "file_name": ""},
                    {"date": "2024-01-02", "value": 5, "file_name": ""},
                ],
            }
        ],
    }


def chart_report_context() -> dict:
    """Minimal context for templates/reports_chart.html: one chart card with a
    summary, a stacked chart, a heat grid and a data table (partials/_charts.html)."""
    datasets = [
        {"label": "JHOVE", "data": [2.0, 0.5], "backgroundColor": "#0072B2", "borderColor": "#0072B2"},
        {"label": "ImageMagick", "data": [1.0, 0], "backgroundColor": "#D55E00", "borderColor": "#D55E00"},
    ]
    description = "Stacked bar chart: Error rate by delivery for Demo. 2 folder(s) in delivery order."
    return {
        "site_env": "dev",
        "site_net": "internal",
        "site_ver": "test",
        "analytics_code": "",
        "username": "",
        "asklogin": True,
        "form": None,
        "project_alias": "demo-project",
        "project_info": {"project_title": "Demo Digitization Project"},
        "report": {"report_id": "folder_error_rates", "report_title": "Error rate by delivery"},
        "chart": {
            "step_id": "folder_error_rates",
            "title": "Error rate by delivery for Demo",
            "empty": False,
            "summary": [{"label": "Folders waiting for QC", "value": 4}],
            "datasets": datasets,
            "chart_js_spec": {
                "step_id": "folder_error_rates", "chart_js_type": "bar", "chart_type": "bar",
                "labels": ["batch_001", "batch_002"], "datasets": datasets,
                "units": "% of files", "title": "Error rate by delivery", "stacked": True,
            },
            "grids": [{
                "title": "Images captured per day",
                "row_header": "Week of",
                "columns": ["Mon", "Tue"],
                "rows": [{"label": "2024-01-01", "cells": [
                    {"text": "H", "level": 0, "title": "2024-01-01: 0 image(s) (holiday)"},
                    {"text": "120", "level": 4, "title": "2024-01-02: 120 image(s)"},
                ]}, {"label": "2024-01-08", "cells": [
                    {"text": "60", "level": 2, "title": "2024-01-08: 60 image(s)"},
                    {"text": "90", "level": 3, "title": "2024-01-09: 90 image(s)"},
                ]}],
            }],
            "note": "A file that fails two checks is counted in both segments.",
            "short_description": description,
            "long_description": description,
            "table_columns": [{"key": "folder", "label": "Folder"}, {"key": "files", "label": "Files"}],
            "table_rows": [{"folder": "batch_001", "files": 400}, {"folder": "batch_002", "files": 380}],
        },
    }


def assert_statistics_a11y(html: str) -> None:
    required = (
        'role="group"',
        "aria-label=",
        "<table",
        "<caption",
        "View chart data table",
        'data-chart-spec=',
    )
    missing = [token for token in required if token not in html]
    if missing:
        raise AssertionError(
            "statistics.html a11y fixture missing: " + ", ".join(missing)
        )


def render_pages() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    env = build_env()

    context = {
        "site_env": "dev",
        "site_net": "internal",
        "site_ver": "test",
        "analytics_code": "",
        "username": "",
        "asklogin": True,
        "project_alias": None,
    }

    pages = {
        "a11y_smoke.html": ("a11y_smoke.html", context),
        "statistics.html": ("statistics.html", statistics_context()),
        "reports_chart.html": ("reports_chart.html", chart_report_context()),
        "report_menus.html": ("a11y_report_menus.html", context),
    }

    for out_name, (template_name, ctx) in pages.items():
        template = env.get_template(template_name)
        html = template.render(**ctx)
        (OUT_DIR / out_name).write_text(html, encoding="utf-8")
        if out_name in ("statistics.html", "reports_chart.html"):
            assert_statistics_a11y(html)


if __name__ == "__main__":
    render_pages()
    print(f"Wrote HTML fixtures to {OUT_DIR}")

