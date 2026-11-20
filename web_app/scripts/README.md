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

6. Apply the EXIF counts table (filled nightly by `scripts/count_exif.py`;
   read by `/sysadmin/schema/`):

   ```bash
   mysql -u <user> -p <db_name> < db/exif_counts.sql
   ```

7. Schedule overnight generation. Copy an entry from
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

## Comparing the folders of two parallel projects

`compare_project_folders.py` compares the folders of two projects that run in
parallel, where the second must not hold folders the first one does not have.
The two projects keep their folders in different tables, so the comparison is
asymmetric by default:

| | project 1 (`folders`) | project 2 (`transcription_folders`) |
| --- | --- | --- |
| name | `project_folder` (nullable) | `folder` (NOT NULL) |
| id | `folder_id` | `folder_transcription_id` |

Project 2's id is `folder_transcription_id`, the uid the app joins on, not the
surrogate `table_id`. Both are selected `AS folder_id`, so the report, CSV and
JSON have one shape; the console detail still names the column each id came
from, and says `no folder_transcription_id` for the rows where it is NULL.

`folders_transcription` is a similarly named legacy table with no callers in
the app; `transcription_folders` is the live one.

It reports:

* **EXTRA in project 2** — folders project 1 does not have. These break the
  rule, so the script exits `1`.
* **MISSING from project 2** — folders project 1 has that project 2 has not
  received yet. Informational by default; `--strict` makes these exit `1` too.
* **IN BOTH** — matched folders, with each side's id and file count. Shown with
  `--show-matches`, and always present in `--json`. A matched pair whose file
  counts differ is highlighted: same folder, different contents.

It also flags duplicate folder names within either project, since those
make the comparison ambiguous.

Each project is named by its `project_alias` or its numeric `project_id`:

```bash
export PYTHONPATH=.
python scripts/compare_project_folders.py <project1> <project2>
```

Useful options:

| Option | Effect |
| --- | --- |
| `--strict` | Exit non-zero on missing folders as well as extra ones |
| `--case-sensitive` | Compare names case-sensitively (the default follows the column's `utf8mb3_general_ci` collation) |
| `--no-details` | Print folder names only, without `folder_id`/date/file counts |
| `--csv PATH` | Also write the comparison to CSV (`--csv-include-shared` adds the matched folders) |
| `--json` | Print the result as JSON instead of the console report |
| `--show-matches` | Also list the folders present in both projects |
| `--no-color` | Disable ANSI colors (also off automatically when piped) |
| `--project1-source`, `--project2-source` | Pick the table per project (`folders` or `transcription_folders`) to compare two projects of the same kind |

It warns on stderr when a project's `projects.transcription` flag disagrees
with the table it is being read from, but still runs: the flags are there to be
used.

Exit codes: `0` clean, `1` differences that count as failures, `2` a bad
project name or other error. That makes it usable from cron as a guard:

```bash
cd /path/to/web_app && PYTHONPATH=. python scripts/compare_project_folders.py main_scan derivative --no-color
```

### SQL-only version

`compare_project_folders.sql` does the same comparison as a plain query, with
the same two tables and the same `folder_transcription_id AS folder_id` for
project 2, for when running the Python script is inconvenient. Set the two
aliases at the top of the file, then:

```bash
mysql -u <user> -p <db_name> < scripts/compare_project_folders.sql
```

It emits three result sets. The first is the comparison, with three kinds of
row in order: `EXTRA in project 2` (the violation), `MISSING from project 2`
(the gaps), and `IN BOTH` (the matches). Its columns are symmetric per project,
so a matched row carries both ids, both file counts and both dates, while an
`EXTRA`/`MISSING` row leaves the absent side NULL. The second lists duplicate
folder names within either project, and the third is a one-row summary where
`extra_in_project2` must be `0` for the rule to hold.

Unlike the script, the query always returns the matches — filter with
`WHERE issue <> 'IN BOTH'` if you only want the discrepancies. Note also that
for a duplicated folder name the query's reported id and date may come from
different physical rows, since they are independent aggregates; the script
reports one whole row per name instead. Result set 2 names exactly the folders
this can affect.

The comparison key is `TRIM(project_folder) COLLATE utf8mb3_general_ci`, stated
explicitly rather than inherited through `TRIM()`, so the case-insensitive
behavior is pinned and visible. Switch both derived tables to
`COLLATE utf8mb3_bin` for a case-sensitive comparison.

The file ends with a variant suitable for storing in `data_reports.query`, which
inlines the aliases because `reports.py` runs stored report SQL with no
parameters and cannot see `@variables` set by a separate statement.

Unlike the Python script, the SQL has no exit code, so it reports rather than
guards. Use the script when you want cron to fail on a violation.
