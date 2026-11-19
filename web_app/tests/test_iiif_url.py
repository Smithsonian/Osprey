"""The IIIF (Cantaloupe) base URL comes from settings.iiif_url."""

import pytest

import settings
from osprey import files


@pytest.fixture
def iiif_file(monkeypatch, tmp_path):
    (tmp_path / 'folder7').mkdir()
    (tmp_path / 'folder7' / 'img001.jpg').write_bytes(b'')
    monkeypatch.setattr(settings, 'iiif_enabled', True, raising=False)
    monkeypatch.setattr(settings, 'iiif_path', str(tmp_path), raising=False)
    monkeypatch.setattr(files, '_dzi_available', lambda *a, **k: False)


def _iiif_image():
    viewer = files.resolve_image_viewer(7, 1, 'img001')
    assert viewer['zoom_exists'] == 2
    return viewer['iiif_image']


def test_default_matches_previous_hardcoded_path(monkeypatch, iiif_file):
    monkeypatch.delattr(settings, 'iiif_url', raising=False)
    assert _iiif_image() == '/iiif/3/folder7__img001/info.json'


def test_full_url_and_trailing_slash(monkeypatch, iiif_file):
    monkeypatch.setattr(settings, 'iiif_url', 'https://iiif.example.org/iiif/2/', raising=False)
    assert _iiif_image() == 'https://iiif.example.org/iiif/2/folder7__img001/info.json'
