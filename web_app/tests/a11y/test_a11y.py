"""Accessibility checks: render templates statically, then run axe in headless Chromium.

Fails on serious or critical violations. Skipped unless Playwright is installed
(`pip install playwright && playwright install chromium`) and axe.min.js has
been fetched by scripts/sync_vendor.py.
"""

from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from tests.a11y.render_a11y_pages import OUT_DIR, render_pages  # noqa: E402

AXE_JS = Path(__file__).resolve().parent / "axe.min.js"


@pytest.fixture(scope="module")
def browser_page():
    if not AXE_JS.exists():
        pytest.skip("tests/a11y/axe.min.js missing; run scripts/sync_vendor.py")
    render_pages()
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


@pytest.mark.parametrize("page_name", ["a11y_smoke.html", "statistics.html", "reports_chart.html", "report_menus.html"])
def test_no_serious_a11y_violations(browser_page, page_name):
    browser_page.goto((OUT_DIR / page_name).as_uri())
    browser_page.add_script_tag(path=str(AXE_JS))
    results = browser_page.evaluate("axe.run()")

    serious = [v for v in results["violations"] if v.get("impact") in ("serious", "critical")]
    report = []
    for v in serious:
        report.append(f"- [{v['impact']}] {v['id']}: {v['help']}")
        for n in v["nodes"][:5]:
            report.append(f"  - {', '.join(n['target'])}: {n.get('failureSummary') or ''}")
    assert not serious, f"A11Y violations in {page_name}:\n" + "\n".join(report)
