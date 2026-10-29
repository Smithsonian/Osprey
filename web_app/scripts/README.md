# Overnight report materialization

Large `data_reports` rows should use `pregenerated = 1` so the web app never runs
their SQL in-request. Artifacts (CSV/XLSX) and a MySQL staging table are built
out-of-band.

## One-time setup

1. Apply tracking table DDL:

   ```bash
   mysql -u <user> -p <db_name> < db/report_materializations.sql
   ```

2. Mark large reports as export mode (edit `report_id` values first):

   ```bash
   mysql -u <user> -p <db_name> < db/mark_pregenerated_reports.sql
   ```

3. For transcription projects, apply the transcription profile tables
   (the nightly queue adds one `transcription_profile` job per
   transcription project):

   ```bash
   mysql -u <user> -p <db_name> < db/transcription_profile.sql
   ```

4. Apply the sysadmin stats table (the nightly queue adds one
   `stat:<job>` built-in job per entry in
   `osprey/services/sysadmin_stats.py`; results show on `/sysadmin/schema/`):

   ```bash
   mysql -u <user> -p <db_name> < db/sysadmin_stats.sql
   ```

5. Apply the sysadmin-only reports table (pregenerated rows are queued as
   `sysrep:<report_id>` jobs; output goes to `sysadmin_reports_folder`,
   outside `static/`):

   ```bash
   mysql -u <user> -p <db_name> < db/sysadmin_reports.sql
   ```

6. Schedule overnight generation. Copy an entry from
   [`cron/nightly_reports.cron.example`](cron/nightly_reports.cron.example), or run:

   ```bash
   ./scripts/run_nightly_reports.sh
   ```

## Manual validation

From the `web_app` root (with `settings.py` and DB credentials configured):

```bash
export PYTHONPATH=.
python scripts/queue_nightly_reports.py
python scripts/materialize_reports.py --until-empty
# Or process a single job:
python scripts/materialize_reports.py --once
```

Then open a pregenerated report in the dashboard: you should see CSV/XLSX
download links and a 20-row preview table.

## Archiving EXIF rows

`exif_export/archive_exif.py` exports a project's `files_exif` rows to a zip
and deletes them. It is standalone (own settings and requirements) and run
by hand, not from the nightly job; see
[exif_export/README.md](exif_export/README.md).

## Backfilling the QC method

`backfill_qc_method.sql` is a one-time script, run after
`db/add_qc_method.sql`. It sets `qc_method = 'weighted'` on folder QC results
(`qc_folders`, `transcription_qc_folders`) saved since the weighted rule went
live (2026-10-15 11:15). It keeps each row's `updated_at`, and is safe to re-run:

```bash
mysql -u <user> -p <db_name> < scripts/backfill_qc_method.sql
```
