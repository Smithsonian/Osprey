# Worker smoke test checklist

After deploying the unified app, verify these endpoints against a staging database:

1. `GET /api/` — returns JSON route catalog with `sys_ver`, `env`, `net` (no auth)
2. `GET /api/projects/` — returns project list and `last_update` (no auth)
3. `POST /api/folders/<folder_id>` with valid `api_key` — returns folder + files (flat check columns)
4. `GET /api/folders/<folder_id>/files` — returns folder + files with `file_checks` arrays (no auth; used by dashboard)
5. `POST /api/update/<project_alias>` with admin `api_key`, `type=startup` — returns `{"result": true}`
6. `POST /api/update/<project_alias>` with admin `api_key`, `type=folder`, `folder_id`, `property=preview_type`, `value=dzi` (or `iiif`) — returns `{"result": true}` and sets folder `preview_type` + badge
7. `POST /api/new/<project_alias>` with admin `api_key` — create folder/file smoke test on a pilot project
8. `POST /api/projects/<project_alias>/recalculate-stats` with admin `api_key` — returns `{"result": true, "folders_processed": N, "folders": [...]}`; optional `status=0` limits to active folders
9. After step 8, `GET /api/projects/<alias>` (no auth) folder rows should match the dashboard folder sidebar for the same project

Compare `/api/projects/<alias>` folder rows with the dashboard folder sidebar for the same project.

Website-facing reads (no auth): `/api/`, `/api/projects/`, `/api/projects/<alias>`, `/api/projects/<alias>/files`, `/api/folders/<id>/files`, `/api/folders/<id>/qc`, `/api/folders/<id>/transcription_qc`.
Worker/admin writes and legacy flat endpoints still require an `api_key`.
