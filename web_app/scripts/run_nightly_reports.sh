#!/usr/bin/env bash
# Overnight pregenerated report refresh.
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

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  if [[ -x "${APP_ROOT}/venv/bin/python" ]]; then
    PYTHON="${APP_ROOT}/venv/bin/python"
  else
    PYTHON="$(command -v python3)"
  fi
fi

export PYTHONPATH="${APP_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

echo "$(date -Is) queueing pregenerated reports"
"${PYTHON}" scripts/queue_nightly_reports.py

echo "$(date -Is) materializing until queue empty"
"${PYTHON}" scripts/materialize_reports.py --until-empty

echo "$(date -Is) nightly reports complete"
