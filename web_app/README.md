# Osprey Web App

Flask dashboard for the Smithsonian Digitization Program Office (DPO)
digitization workflows: project dashboards, folder/file tracking, QC
(visual and transcription), reports, and invoice reconciliation. A
separate worker API under `/api/` receives updates from the Osprey
worker processes.

## Layout

- `app.py` — Flask app, login, dashboard and QC routes
- `web/` — blueprints for files, projects, reports, invoices
- `api/` — worker/read API blueprint (`/api/...`)
- `osprey/` — DB pool (`osprey/db.py`) and service layer (`osprey/services/`)
- `templates/`, `static/` — Jinja2 templates and assets
- `scripts/` — nightly pregenerated-report jobs (see `scripts/README.md`)
- `db/` — SQL applied by hand for the report materialization tables
- `tests/` — pytest suite and the axe-based a11y checks (`tests/a11y/`)

## Setup

Requires Python 3.9+ and MySQL. The full database schema lives outside
this directory (`osprey_database_structure.sql` in the parent project).

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
cp settings.py.template settings.py
```

Configuration is read from `settings.py`, which takes every value from
environment variables (see the template for the full list: `DB_HOST`,
`DB_USER`, `DB_PASSWORD`, `SECRET_KEY`, `LDAP_SERVER`, ...).
`settings.py` is gitignored — never commit credentials.

## Run (development)

```bash
OSPREY_ENV=dev venv/bin/python app.py
```

This starts the Werkzeug dev server. Production runs behind a real WSGI
server; `settings.py`'s `OSPREY_ENV=prod` switches on response
minification. Logging is verbose only when `OSPREY_ENV=dev`; any other
value logs WARNING and above.

## Logging

`logger.py` writes two files in `OSPREY_LOG_FOLDER` (default `logs/`):
`ospreyapp.log` (app, scripts) and `ospreyapi.log` (`api/` blueprint).
Names are fixed, so all gunicorn workers and the nightly scripts append to
the same files. The app does **not** rotate them: without a logrotate
rule they grow forever. Example `/etc/logrotate.d/osprey` (adjust paths
and user):

```
/path/to/web_app/logs/ospreyapp.log /path/to/web_app/logs/ospreyapi.log {
    daily
    maxsize 100M
    rotate 14
    compress
    missingok
    notifempty
    su appuser appgroup
}
```

`maxsize` is only checked when logrotate runs (daily by default on RHEL).
On RHEL with SELinux, a non-standard log folder may need the `var_log_t`
label or logrotate will be denied (check `ausearch -m avc -ts recent`).

## Tests

```bash
venv/bin/python -m pytest tests/
```

The suite stubs the database and does not need MySQL. Accessibility
checks (renders templates statically, then runs axe via Playwright):

```bash
npm install
npm run a11y
```

## Nightly reports

Pregenerated report exports are queued and materialized out-of-band:

```bash
./scripts/run_nightly_reports.sh
```

Cron example in `scripts/cron/nightly_reports.cron.example`; details in
`scripts/README.md`.

## Security notes

- All configuration secrets (DB, LDAP, ArchivesSpace, `SECRET_KEY`)
  must come from environment variables. If a credential has ever been
  stored in a synced or shared copy of `settings.py`, rotate it.
- `static/reports/` and `static/image_previews/` hold generated data
  and are gitignored.
