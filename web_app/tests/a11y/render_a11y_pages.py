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


def build_env() -> Environment:
    loader = FileSystemLoader([str(TEST_TEMPLATES), str(ROOT / "templates")])
    env = Environment(
        loader=loader,
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    )
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
    }

    for out_name, (template_name, ctx) in pages.items():
        template = env.get_template(template_name)
        html = template.render(**ctx)
        (OUT_DIR / out_name).write_text(html, encoding="utf-8")
        if out_name == "statistics.html":
            assert_statistics_a11y(html)


if __name__ == "__main__":
    render_pages()
    print(f"Wrote HTML fixtures to {OUT_DIR}")

