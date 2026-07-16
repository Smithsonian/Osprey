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

3. Schedule overnight generation. Copy an entry from
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
