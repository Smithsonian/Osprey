#!/usr/bin/env bash
# Overnight pregenerated report refresh.
#
# First recalculates projects_stats for ongoing projects and stores this
# year's new images and objects per project (scripts/nightly_project_stats.py),
# and counts files_exif rows per project (scripts/count_exif.py).
#
# Queues every data_reports row with pregenerated=1, then drains the
# report_materializations queue until empty.
#
# Usage (from the web_app root, with settings.py available):
#   ./scripts/run_nightly_reports.sh
#
# Cron example (2:00 AM): see scripts/cron/nightly_reports.cron.example

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${APP_ROOT}"

# rm old reports (guard the glob: with set -e an empty dir would abort the run)
mkdir -p static/reports
find static/reports -mindepth 1 -maxdepth 1 -type f -delete

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  if [[ -x "${APP_ROOT}/venv/bin/python" ]]; then
    PYTHON="${APP_ROOT}/venv/bin/python"
  else
    PYTHON="$(command -v python3)"
  fi
fi

export PYTHONPATH="${APP_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

# Recalculate ongoing projects' totals, then store this year's new images and
# objects per project for the homepage's "+N in <year>". Its failure
# (e.g. db/projects_stats_yearly.sql not applied yet) must not stop the reports.
echo "$(date -Is) recalculating project totals and this year's counts"
"${PYTHON}" scripts/nightly_project_stats.py || echo "$(date -Is) WARNING: project stats step reported problems"

# Count files_exif rows per project for /sysadmin/schema/. Its failure
# (e.g. db/exif_counts.sql not applied yet) must not stop the reports.
echo "$(date -Is) counting EXIF rows per project"
"${PYTHON}" scripts/count_exif.py || echo "$(date -Is) WARNING: EXIF count step failed; see the app log"

echo "$(date -Is) queueing pregenerated reports"
"${PYTHON}" scripts/queue_nightly_reports.py

echo "$(date -Is) materializing until queue empty"
"${PYTHON}" scripts/materialize_reports.py --until-empty

echo "$(date -Is) nightly reports complete"
