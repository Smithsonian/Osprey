# Worker smoke test checklist

After deploying the unified app, verify these endpoints against a staging database:

1. `GET /api/` — returns JSON route catalog with `sys_ver`, `env`, `net`
2. `GET /api/projects/` — returns project list and `last_update`
3. `POST /api/folders/<folder_id>` with valid `api_key` — returns folder + files (flat check columns)
4. `GET /api/folders/<folder_id>/files` — returns folder + files with `file_checks` arrays (no `api_key`; used by dashboard)
5. `POST /api/update/<project_alias>` with admin `api_key`, `type=startup` — returns `{"result": true}`
6. `POST /api/new/<project_alias>` with admin `api_key` — create folder/file smoke test on a pilot project

Compare `/api/projects/<alias>` folder rows with the dashboard folder sidebar for the same project.
