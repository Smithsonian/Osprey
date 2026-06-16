"""Project file search queries for the dashboard."""

from osprey.db import run_query
from osprey.files import static_preview_path

PAGE_SIZE = 50


def _like_pattern(q):
    return '%' + q + '%'


def get_project_info(project_alias):
    rows = run_query(
        "SELECT * FROM projects WHERE project_alias = %(project_alias)s",
        {'project_alias': project_alias},
    )
    if not rows:
        return None
    return rows[0]


def _select_sql(transcription):
    if transcription:
        return (
            "SELECT f.file_transcription_id, f.folder_transcription_id, f.file_name, "
            " f.preview_image, fd.folder "
            " FROM transcription_files f "
            " INNER JOIN transcription_folders fd ON f.folder_transcription_id = fd.folder_transcription_id "
            " INNER JOIN projects p ON fd.project_id = p.project_id "
        )
    return (
        "SELECT f.file_id, f.folder_id, f.file_name, f.preview_image, fd.project_folder "
        " FROM files f "
        " INNER JOIN folders fd ON f.folder_id = fd.folder_id "
        " INNER JOIN projects p ON fd.project_id = p.project_id "
    )


def _count_sql(transcription):
    where = (
        "p.project_alias = %(project_alias)s AND lower(f.file_name) LIKE lower(%(q)s)"
    )
    if transcription:
        return (
            "SELECT COUNT(*) as total "
            " FROM transcription_files f "
            " INNER JOIN transcription_folders fd ON f.folder_transcription_id = fd.folder_transcription_id "
            " INNER JOIN projects p ON fd.project_id = p.project_id "
            " WHERE " + where
        )
    return (
        "SELECT COUNT(*) as total "
        " FROM files f "
        " INNER JOIN folders fd ON f.folder_id = fd.folder_id "
        " INNER JOIN projects p ON fd.project_id = p.project_id "
        " WHERE " + where
    )


def search_files(project_alias, q, page=0):
    """Return (project_info, results, total, page, page_size) or (None, ...) if project missing."""
    project_info = get_project_info(project_alias)
    if project_info is None:
        return None, [], 0, page, PAGE_SIZE

    transcription = project_info['transcription'] == 1
    params = {'project_alias': project_alias, 'q': _like_pattern(q)}
    offset = page * PAGE_SIZE

    total = run_query(_count_sql(transcription), params)[0]['total']
    results = run_query(
        (_select_sql(transcription)
         + " WHERE p.project_alias = %(project_alias)s AND lower(f.file_name) LIKE lower(%(q)s)"
         + " ORDER BY f.file_name"
         + " LIMIT {limit} OFFSET {offset}").format(limit=PAGE_SIZE, offset=offset),
        params,
    )
    results = [enrich_result(row, transcription) for row in results]
    return project_info, results, total, page, PAGE_SIZE


def enrich_result(row, transcription):
    """Attach preview paths for template rendering."""
    if transcription:
        file_id = row['file_transcription_id']
        folder_id = row['folder_transcription_id']
    else:
        file_id = row['file_id']
        folder_id = row['folder_id']

    preview_image = row.get('preview_image')
    if preview_image and ('://' in preview_image or preview_image.startswith('/')):
        row['preview_image_ext'] = preview_image
    else:
        row['preview_image_ext'] = None

    row['preview_img_path'] = static_preview_path(
        folder_id, file_id, size='160', transcription=transcription,
    )
    return row
