"""File ID validation and static preview path helpers."""

import logging
import os
from uuid import UUID

import settings
from osprey.db import run_query

logger = logging.getLogger(__name__)


def check_file_id(file_id=None):
    """Return (file_id, uid) or (False, False) for int or UUID file identifiers."""
    if file_id is None:
        return False, False
    try:
        file_id = int(file_id)
        file_id_type = "int"
    except ValueError:
        try:
            file_uid = UUID(file_id, version=4)
            file_id_type = "uuid"
        except ValueError:
            return False, False
    if file_id_type == "uuid":
        rows = run_query("SELECT file_id FROM files WHERE uid = %(uid)s", {'uid': file_uid})
        if len(rows) == 0:
            return False, False
        return rows[0]['file_id'], file_uid
    rows = run_query("SELECT uid FROM files WHERE file_id = %(file_id)s", {'file_id': file_id})
    if len(rows) == 0:
        return False, False
    return file_id, rows[0]['uid']


def _preview_base_path(folder_id, file_id, transcription=False):
    if transcription:
        return f"image_previews/{folder_id}"
    return f"image_previews/folder{folder_id}"


def static_preview_path(folder_id, file_id, size="160", transcription=False):
    """Return a static/ relative path for a sized preview, or na_{size}.png fallback."""
    path = f"{_preview_base_path(folder_id, file_id, transcription)}/{size}/{file_id}.jpg"
    if os.path.isfile(f"static/{path}"):
        return path
    if size in ("160", "200", "600", "800", "1200"):
        return f"na_{size}.png"
    return "na_160.png"


def resolve_static_preview_fallback(folder_id, file_id, transcription=False):
    """Prefer 800px, then 160px; return relative static path or None if neither exists."""
    base = _preview_base_path(folder_id, file_id, transcription)
    for size in ("800", "160"):
        path = f"{base}/{size}/{file_id}.jpg"
        if os.path.isfile(f"static/{path}"):
            return path
    return None


def static_fullsize_path(folder_id, file_id, transcription=False):
    """Return the best available static path for a full-size JPG preview."""
    base = _preview_base_path(folder_id, file_id, transcription)
    for candidate in (
        f"{base}/{file_id}.jpg",
        f"{base}/600/{file_id}.jpg",
        f"{base}/160/{file_id}.jpg",
    ):
        if os.path.isfile(f"static/{candidate}"):
            return candidate
    return static_preview_path(folder_id, file_id, size="600", transcription=transcription)


def attach_preview_paths(file_details, file_id, transcription=False):
    """Add preview_img_path, preview_img_path_600, and fullsize_img_path to file_details."""
    if transcription:
        folder_id = file_details['folder_transcription_id']
    else:
        folder_id = file_details['folder_id']
    file_details['preview_img_path'] = static_preview_path(
        folder_id, file_id, size="160", transcription=transcription
    )
    file_details['preview_img_path_600'] = static_preview_path(
        folder_id, file_id, size="600", transcription=transcription
    )
    file_details['fullsize_img_path'] = static_fullsize_path(
        folder_id, file_id, transcription=transcription
    )
    file_details['preview_fallback_path'] = resolve_static_preview_fallback(
        folder_id, file_id, transcription=transcription
    )
    return file_details


def _iiif_disk_dir(folder_id, transcription=False):
    if transcription:
        return str(folder_id)
    return f"folder{folder_id}"


def _iiif_manifest_id(folder_id, file_name, transcription=False):
    prefix = _iiif_disk_dir(folder_id, transcription)
    return f"{prefix}__{file_name}"


def _dzi_available(preview_base, file_id):
    """Return True if a DZI manifest exists for this file."""
    return os.path.isfile(f"static/{preview_base}/{file_id}.dzi")


def resolve_image_viewer(folder_id, file_id, file_name, *, transcription=False):
    """Resolve DZI or IIIF OpenSeadragon source for a file preview.

    Returns zoom_exists (0=none, 1=DZI, 2=IIIF), zoom_filename, and iiif_image.
    """
    preview_base = _preview_base_path(folder_id, file_id, transcription)
    zoom_exists = 0
    zoom_filename = None
    iiif_image = None

    if _dzi_available(preview_base, file_id):
        zoom_exists = 1
        zoom_filename = f"../../static/{preview_base}/{file_id}.dzi"

    if settings.iiif_enabled:
        iiif_dir = _iiif_disk_dir(folder_id, transcription)
        jpg_path = f"{settings.iiif_path}/{iiif_dir}/{file_name}.jpg"
        iiif_found = os.path.isfile(jpg_path)
        logger.info(
            "IIIF lookup for file_id=%s: jpg_path=%s found=%s",
            file_id, jpg_path, iiif_found,
        )
        if iiif_found:
            zoom_exists = 2
            manifest_id = _iiif_manifest_id(folder_id, file_name, transcription)
            iiif_image = f"/iiif/3/{manifest_id}/info.json"
    else:
        logger.info("IIIF lookup for file_id=%s: skipped (iiif_enabled=False)", file_id)

    return {
        "zoom_exists": zoom_exists,
        "zoom_filename": zoom_filename,
        "iiif_image": iiif_image,
    }
