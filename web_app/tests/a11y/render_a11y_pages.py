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
    )
    return env


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
        "a11y_smoke.html": "a11y_smoke.html",
    }

    for out_name, template_name in pages.items():
        template = env.get_template(template_name)
        html = template.render(**context)
        (OUT_DIR / out_name).write_text(html, encoding="utf-8")


if __name__ == "__main__":
    render_pages()
    print(f"Wrote HTML fixtures to {OUT_DIR}")

