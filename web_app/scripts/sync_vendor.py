#!/usr/bin/env python3
"""Download the pinned frontend libraries and copy their dist files into static/vendor/.

templates/base.html (and the chart pages) load these from static/vendor/ so
they don't depend on a CDN at runtime. Each package is fetched as its npm
tarball straight from the registry; no Node or npm is needed. To bump a
version, edit PACKAGES below, run this script, and commit the changed files
under static/vendor/.

Also fetches axe-core into tests/a11y/ for the accessibility test (test-only,
not served).

Run with: python3 scripts/sync_vendor.py [--out DIR]
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "static" / "vendor"
A11Y = ROOT / "tests" / "a11y"

PACKAGES = {
    "@fortawesome/fontawesome-free": "6.4.2",
    "bootstrap": "5.3.8",
    "chart.js": "4.4.7",
    "chartjs-adapter-date-fns": "3.0.0",
    "datatables.net": "2.3.7",
    "datatables.net-buttons": "3.2.6",
    "datatables.net-buttons-dt": "3.2.6",
    "datatables.net-dt": "2.3.7",
    "jquery": "4.0.0",
    "jszip": "3.10.1",
}

# (package, path inside the package, destination under static/vendor/).
# A path ending in "/" copies that directory recursively.
FILES = [
    ("bootstrap", "dist/css/bootstrap.min.css", "bootstrap/bootstrap.min.css"),
    ("bootstrap", "dist/js/bootstrap.bundle.min.js", "bootstrap/bootstrap.bundle.min.js"),

    # css/ and webfonts/ must stay siblings, matching the npm package layout:
    # all.min.css references fonts via a relative `../webfonts/...` url().
    ("@fortawesome/fontawesome-free", "css/all.min.css", "fontawesome/css/all.min.css"),
    ("@fortawesome/fontawesome-free", "webfonts/", "fontawesome/webfonts/"),

    ("jquery", "dist/jquery.min.js", "jquery/jquery.min.js"),

    ("datatables.net-dt", "css/dataTables.dataTables.min.css", "datatables/dataTables.dataTables.min.css"),
    ("datatables.net-dt", "js/dataTables.dataTables.min.js", "datatables/dataTables.dataTables.min.js"),
    ("datatables.net", "js/dataTables.min.js", "datatables/dataTables.min.js"),
    ("datatables.net-buttons", "js/dataTables.buttons.min.js", "datatables/dataTables.buttons.min.js"),
    ("datatables.net-buttons", "js/buttons.html5.min.js", "datatables/buttons.html5.min.js"),
    ("datatables.net-buttons-dt", "js/buttons.dataTables.min.js", "datatables/buttons.dataTables.min.js"),

    ("jszip", "dist/jszip.min.js", "jszip/jszip.min.js"),

    # chart.js stopped publishing a pre-minified UMD build to npm (jsdelivr
    # minifies dist/chart.umd.js on the fly for the .min.js CDN URL); ship the
    # unminified file instead. It's identical bytes to what Flask-Minify
    # already produces for our own static/js/*.js in prod, so this costs
    # nothing at runtime.
    ("chart.js", "dist/chart.umd.js", "chartjs/chart.umd.js"),
    ("chartjs-adapter-date-fns", "dist/chartjs-adapter-date-fns.bundle.min.js",
     "chartjs/chartjs-adapter-date-fns.bundle.min.js"),
]

AXE_VERSION = "4.12.1"


def fetch_tarball(name: str, version: str) -> tarfile.TarFile:
    basename = name.rsplit("/", 1)[-1]
    url = f"https://registry.npmjs.org/{name}/-/{basename}-{version}.tgz"
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = resp.read()
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")


def extract(tar: tarfile.TarFile, src: str, dest: Path) -> int:
    """Copy one file, or every file under a directory, from the tarball's package/ root."""
    prefix = f"package/{src}"
    count = 0
    for member in tar.getmembers():
        if not member.isfile():
            continue
        if src.endswith("/"):
            if not member.name.startswith(prefix):
                continue
            target = dest / member.name[len(prefix):]
        elif member.name == prefix:
            target = dest
        else:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with tar.extractfile(member) as fsrc, open(target, "wb") as fdst:
            shutil.copyfileobj(fsrc, fdst)
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=VENDOR, help="destination (default: static/vendor/)")
    args = parser.parse_args()

    tarballs = {name: fetch_tarball(name, version) for name, version in PACKAGES.items()}

    missing = 0
    for package, src, dest in FILES:
        if extract(tarballs[package], src, args.out / dest):
            print(f"vendored: {dest}")
        else:
            print(f"missing: {package}/{src}", file=sys.stderr)
            missing += 1

    if extract(fetch_tarball("axe-core", AXE_VERSION), "axe.min.js", A11Y / "axe.min.js"):
        print("fetched: tests/a11y/axe.min.js")
    else:
        print("missing: axe-core/axe.min.js", file=sys.stderr)
        missing += 1

    if missing:
        print(f"{missing} package file(s) missing; vendor sync incomplete.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
