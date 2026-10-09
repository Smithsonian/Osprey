# Osprey Web App

Flask dashboard for the Smithsonian Digitization Program Office (DPO)
digitization workflows: project dashboards, folder/file tracking, QC
(visual and transcription), reports, and invoice reconciliation. A
separate worker API under `/api/` receives updates from the Osprey
worker processes.

## Layout

- `app.py` — Flask app, login, dashboard and QC routes
- `web/` — blueprints for files, projects, reports, invoices, sysadmin
- `api/` — worker/read API blueprint (`/api/...`)
- `osprey/` — DB pool (`osprey/db.py`) and service layer (`osprey/services/`)
- `templates/`, `static/` — Jinja2 templates and assets
- `scripts/` — nightly pregenerated-report jobs (see `scripts/README.md`)
- `db/` — SQL applied by hand for the report materialization and transcription profile tables, and `users.sysadmin`
- `tests/` — pytest suite and the axe-based a11y checks (`tests/a11y/`)

## View conventions

Shared plumbing lives at the app level, so routes (in `app.py` and in the
`web/` blueprints) don't repeat it:

- **Template context** — `inject_site_context()` in `app.py` adds
  `site_env`, `site_net`, `site_ver` and `analytics_code` to every
  template. Don't pass them to `render_template()`; an explicit kwarg with
  the same name still overrides the injected value if a view needs to.
- **Error pages** — `render_error(error_msg, status_code, project_alias=None)`
  in `web/errors.py` renders `error.html` and returns `(body, status)`.
  With `project_alias`, the page's "Go back" link points to that
  project's dashboard; otherwise it points to the homepage.
- **API-only deployments** — when `site_net == "api"`,
  `redirect_web_routes_on_api_site()` (a `before_request` hook) sends every
  browser route to the API route list (`/api/`). The API blueprint, static
  files, the favicon and unmatched URLs (404) are not redirected. New
  routes get this automatically; no per-route check is needed.

## QC decision

A folder's QC Passed / QC Failed result is computed by
`folder_passes_qc()` in `osprey/services/qc.py`, called from
`qc_process()` (image folders) and `qc_process_transcript()`
(transcription folders) in `app.py`.

**Input:** the sample size (`qc_files` rows for the folder), the number of
sampled files rated Critical (1), Major (2) and Minor (3), and the
project's `qc_settings` row (`qc_threshold_critical`, `qc_threshold_major`,
`qc_threshold_minor`, in percent).

**Rule (cumulative severities):** each issue also counts against the
thresholds of the less severe categories:

| Check    | Counted issues            | Fails when % is over      |
|----------|---------------------------|---------------------------|
| Critical | critical                  | `qc_threshold_critical`   |
| Major    | critical + major          | `qc_threshold_major`      |
| Minor    | critical + major + minor  | `qc_threshold_minor`      |

So `qc_threshold_minor` is effectively the cap on *all* issues combined.
Equal to the threshold passes; only exceeding it fails.

Example, 400-file sample with defaults (0 / 1.5 / 4): 6 major + 10 minor
= 4.0% total → passes; 6 major + 16 minor = 5.5% total → fails.

**Output:** `True` (passed) / `False` (failed). Raises `ValueError` on an
empty sample. Results saved before this rule are not recalculated.

**Saving (`qc_done()`, POST only):** the result shown on `qc_done.html` is
display-only. On submit, `qc_done()`:

1. Rejects (403) anyone other than the folder's assigned reviewer
   (`qc_folders.qc_by`, set when `qc_process()` claims the folder).
2. Reloads the sample with `load_folder_qc_counts()` and rejects (400) if
   it is empty or any sampled file is still unrated (`file_qc` 9/NULL).
3. Recomputes pass/fail with `folder_passes_qc()` and saves that. The
   posted `qc_status` is ignored; a mismatch is logged as a warning.

Transcription *source* QC (`qc_transcription_done()`) is a separate flow
and still takes the posted value.

## Dashboard folder filters (transcription projects)

The folder list on the project dashboard (`static/js/dashboard_folders.js`,
`matchesFilter()`) is loaded from `GET /api/projects/<alias>`, which uses
`list_for_project()` in `osprey/services/folders.py`.

For transcription projects each folder row has `has_transcriptions`
(1/0): 1 when at least one file in the folder has a
`transcription_files_text` row, from any source. Image projects don't
send the field, so it is treated as 0.

| Filter                     | Folders shown                                                          |
|----------------------------|------------------------------------------------------------------------|
| Transcribed                | `has_transcriptions = 1` (shown even when project QC is off)           |
| Transcription QC Passed    | transcribed, available, has a "Transcription QC Passed" badge, no Failed badge |
| Transcription QC Failed    | transcribed, has any "Transcription QC Failed" badge                   |
| Transcription QC Pending   | transcribed, available, no transcription QC badge yet                  |

The three Transcription QC filters only appear when project QC is on.
Pass/fail per source comes from the `transcription_qc_status` badges
written by `qc_transcription_done()`.

## Transcription profile

A built-in report (`report_id = transcription_profile`, transcription
projects only) that profiles the transcribed text of each transcription
source in three tabs:

1. **Fill rate**: per field, the share of transcribed files that are
   *filled*, *NonString* or *empty*. NonString = the value is only marks
   (the `!!!` illegible marker, `--`, `?`, ...) or a listed `nonstring`
   term (`N/A`, `none`, ...). Partly illegible values (`Sm!!! County`)
   count as filled.
2. **Common values**: the most frequent values per field, with
   near-identical spellings grouped together.
3. **Suspicious values**: values that may be errors or hallucinations,
   scored by several signals, with a link to an example file.

The dashboard's File Checks tab also shows a compact fill-rate panel for
the selected folder, linking to the full report.

### Code structure

| File | Role |
|---|---|
| `osprey/services/transcription_profile_analysis.py` | Pure logic (no DB): normalization, fuzzy grouping, scoring |
| `osprey/services/transcription_profile.py` | DB side: settings, streaming rows, storing and reading results |
| `scripts/materialize_reports.py` | Runs the profile when the `transcription_profile` job is claimed |
| `scripts/queue_nightly_reports.py` | Queues one job per transcription project every night |
| `web/reports.py`, `templates/reports_transcription_profile.html` | Report page |
| `api/routes/folders.py` (`/api/folders/<id>/transcription_fill`), `static/js/dashboard_transcription_fill.js` | Dashboard panel |
| `db/transcription_profile.sql` | Tables (apply by hand) |
| `tests/test_transcription_profile.py` | Unit tests for the analysis helpers |

### Input

`transcription_sources` → `transcription_fields` → `transcription_files_text`
(one row per file and field), plus `transcription_files` for each file's
folder. A file counts toward a source's denominator when it has at least
one text row for that source, so folders that have not been transcribed
yet do not lower the fill rate.

### Output (tables in `db/transcription_profile.sql`)

- `transcription_profile_fill`: one row per source, folder and field with
  `total_files`, `filled` and `nonstring` (empty = the rest). The report
  sums it over folders; the dashboard panel reads one folder.
- `transcription_profile_results`: one JSON document per source:
  `{"fields": [{field_name, filled, distinct, free_text, common: [...]}], "suspicious": [...]}`.
- `report_materializations`: run status, duration, rows read (the
  existing table).

A source's rows are deleted and rewritten on each run, so a reader in
that window can briefly see an empty panel.

### How values are compared

Every value is **normalized** first: Unicode NFKC, casefolded, whitespace
collapsed and outer punctuation stripped (`"  Smith, J. "` → `"smith, j"`).
Terms are normalized the same way.

**Grouping** (per field):

1. The `canonical_pool` most frequent distinct values are grouped greedily,
   most frequent first, using rapidfuzz `fuzz.ratio` ≥ `fuzzy_threshold`.
2. Every other value is matched to its closest group head (in chunks with
   `process.cdist`); below the threshold it forms its own group.

This bounds the work to roughly *distinct values × pool size* comparisons.
For example, 300k rows with 120k distinct values takes about 5 s and
under 100 MB.

**Free-text fields** (distinct / filled > `free_text_ratio`, e.g. notes)
are not grouped, and the rarity signals are skipped for them: almost
every value is unique, so "rare" would flag everything.

### Suspicious-value signals

Each signal that fires adds its weight (`w_*` in settings) to the score.
Values with score ≥ `min_score` are kept, then the top `max_suspicious`
across all fields are stored.

| Signal | Fires when |
|---|---|
| `rare` | The value's group has ≤ `rare_max_count` values (not for free text) |
| `novel` | Added to `rare`, scaled by how unlike the closest other value it is (`1 - similarity/100`) |
| `shape` | The value's character shape (letters `a`, digits `9`, runs collapsed: `2024-05-01` → `9-9-9`) is under 1% of the field's values |
| `length` | Length is an outlier: modified z-score > 3.5 (median/MAD) |
| `repeat` | The same word appears 3+ times in a row |
| `boilerplate` | Contains a `boilerplate` term (e.g. "the image shows") |

`shape` and `length` need at least 50 filled values in the field. These
constants are at the top of `transcription_profile_analysis.py`.

### Settings (per project, in the DB)

`transcription_profile_settings` (one row) and `transcription_profile_terms`
(`nonstring` = whole-value match, `boilerplate` = substring match). Both
are seeded with defaults the first time a project is profiled; edit them
with SQL, e.g.:

```sql
UPDATE transcription_profile_settings SET fuzzy_threshold = 85 WHERE project_id = 12;
INSERT INTO transcription_profile_terms (project_id, term_type, term) VALUES (12, 'nonstring', 'sin datos');
```

Changes apply on the next run. `fuzz.ratio` drops quickly on short
strings: one swapped letter in a 5-letter word (`Smith`/`Smiht`) scores
80, so the default 90 leaves those apart.

### Running

Nightly with the other reports (`scripts/run_nightly_reports.sh`). The
report's **Recompute** button (logged-in users) only queues a job; it runs
on the next `materialize_reports.py` pass.

### Requirements

`rapidfuzz` (in `requirements.txt`, uses numpy from pandas), and the four
tables from `db/transcription_profile.sql`:

```bash
mysql -u <user> -p <db_name> < db/transcription_profile.sql
```

## System admin page

`/sysadmin/` (`web/sysadmin.py`, `osprey/services/system_status.py`) is a
read-only status page: app/package versions, DB round-trip and server
version, cache directory size, nightly report status and recent failures,
and the last ERROR/CRITICAL lines of `ospreyapp.log` and `ospreyapi.log`.
A link appears on `/home/` for users who can open it.

- **Who** — users with `users.sysadmin = 1`, and only when
  `site_net == "internal"`. Anyone else is redirected to `/home/`.
- **Two flags** — `is_admin` is for people who manage specific projects;
  `sysadmin` has more powers (system administration). Neither implies the
  other.
- **Schema** — apply `db/sysadmin.sql` *before* deploying: `/home/` reads
  the column on internal sites. Grant with
  `UPDATE users SET sysadmin = 1 WHERE username = '<username>';`.
- Each section fails independently (shown as "Unavailable: ..."), so the
  page still loads when the DB or a log file is the problem.
- Log lines shown come from the last 256 KB of each file; they may contain
  query text, which is why the page is sysadmin-only.

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

This also profiles every transcription project (see "Transcription
profile"). Cron example in `scripts/cron/nightly_reports.cron.example`;
details in `scripts/README.md`.

## Security notes

- All configuration secrets (DB, LDAP, ArchivesSpace, `SECRET_KEY`)
  must come from environment variables. If a credential has ever been
  stored in a synced or shared copy of `settings.py`, rotate it.
- `static/reports/` and `static/image_previews/` hold generated data
  and are gitignored.
