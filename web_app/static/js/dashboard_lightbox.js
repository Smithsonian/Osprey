(function () {
    'use strict';

    var PAGE_SIZE = 25;
    var allFiles = [];
    var currentPage = 1;
    var currentConfig = {};
    var paginationBound = false;

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function panelConfig(panel) {
        return {
            transcription: parseInt(panel.getAttribute('data-transcription') || '0', 10) === 1,
            appRoot: panel.getAttribute('data-app-root') || '',
            folderId: panel.getAttribute('data-folder-id') || ''
        };
    }

    function previewSrc(file, transcription, appRoot, folderId) {
        if (file.preview_image) {
            return file.preview_image + '&max=160';
        }
        var query = transcription ? '?transcription=1' : '';
        return appRoot + '/preview/' + encodeURIComponent(folderId) + '/' + encodeURIComponent(file.file_id) + '/' + query;
    }

    function fileCardHtml(file, transcription, appRoot, folderId) {
        var detailPath = transcription ?
            appRoot + '/file_transcription/' + file.file_id + '/' :
            appRoot + '/file/' + file.file_id + '/';
        var alt = 'Preview image of ' + escapeHtml(file.file_name);
        return '<a type="button" class="btn btn-light btn-sm dashboard-lightbox-card" href="' + detailPath + '" ' +
            'title="Details of the file ' + escapeHtml(file.file_name) + '">' +
            '<img src="' + previewSrc(file, transcription, appRoot, folderId) + '" alt="' + alt + '" ' +
            'style="padding: 10px; max-width: 160px;" class="img-fluid img-thumbnail"><br>' +
            '<small>' + escapeHtml(file.file_name) + '</small>' +
            '</a>';
    }

    function pageItem(label, targetPage, enabled, active) {
        if (!enabled) {
            return '<li class="page-item disabled"><a class="page-link" href="#" tabindex="-1">' + label + '</a></li>';
        }
        return '<li class="page-item' + (active ? ' active' : '') + '">' +
            '<a class="page-link" href="#" data-lightbox-page="' + targetPage + '">' + label + '</a></li>';
    }

    function buildPaginationHtml(page, totalPages) {
        if (totalPages <= 1) {
            return '';
        }
        var html = '<ul class="pagination float-end">';
        html += pageItem('Previous', page - 1, page > 1);

        var start = Math.max(1, page - 3);
        var end = Math.min(totalPages, page + 3);

        if (start > 1) {
            html += pageItem('1', 1, true);
            if (start > 2) {
                html += '<li class="page-item disabled"><a class="page-link" href="#">&hellip;</a></li>';
            }
        }
        for (var i = start; i <= end; i++) {
            html += pageItem(String(i), i, true, i === page);
        }
        if (end < totalPages) {
            if (end < totalPages - 1) {
                html += '<li class="page-item disabled"><a class="page-link" href="#">&hellip;</a></li>';
            }
            html += pageItem(String(totalPages), totalPages, true);
        }

        html += pageItem('Next', page + 1, page < totalPages);
        html += '</ul>';
        return html;
    }

    function renderPage() {
        var totalPages = Math.max(1, Math.ceil(allFiles.length / PAGE_SIZE));
        if (currentPage > totalPages) {
            currentPage = totalPages;
        }
        var start = (currentPage - 1) * PAGE_SIZE;
        var pageFiles = allFiles.slice(start, start + PAGE_SIZE);

        document.getElementById('lightbox-grid').innerHTML = pageFiles.map(function (file) {
            return fileCardHtml(file, currentConfig.transcription, currentConfig.appRoot, currentConfig.folderId);
        }).join('');

        var paginationHtml = buildPaginationHtml(currentPage, totalPages);
        document.getElementById('dashboard-lightbox-pagination-top').innerHTML = paginationHtml;
        document.getElementById('dashboard-lightbox-pagination-bottom').innerHTML = paginationHtml;
    }

    function bindPaginationClicks() {
        if (paginationBound) {
            return;
        }
        paginationBound = true;
        document.getElementById('dashboard-lightbox-content').addEventListener('click', function (event) {
            var link = event.target.closest('[data-lightbox-page]');
            if (!link) {
                return;
            }
            event.preventDefault();
            currentPage = parseInt(link.getAttribute('data-lightbox-page'), 10);
            renderPage();
        });
    }

    function setLoading() {
        document.getElementById('dashboard-lightbox-loading').classList.remove('d-none');
        document.getElementById('dashboard-lightbox-content').classList.add('d-none');
        document.getElementById('dashboard-lightbox-empty').classList.add('d-none');
        document.getElementById('dashboard-lightbox-error').classList.add('d-none');
    }

    function showError(message) {
        document.getElementById('dashboard-lightbox-loading').classList.add('d-none');
        document.getElementById('dashboard-lightbox-content').classList.add('d-none');
        document.getElementById('dashboard-lightbox-empty').classList.add('d-none');
        var errorEl = document.getElementById('dashboard-lightbox-error');
        errorEl.classList.remove('d-none');
        errorEl.textContent = message;
    }

    function showEmpty() {
        document.getElementById('dashboard-lightbox-loading').classList.add('d-none');
        document.getElementById('dashboard-lightbox-content').classList.add('d-none');
        document.getElementById('dashboard-lightbox-error').classList.add('d-none');
        document.getElementById('dashboard-lightbox-empty').classList.remove('d-none');
    }

    function showContent(data, panel) {
        currentConfig = panelConfig(panel);
        allFiles = (data.files || []).slice();
        currentPage = 1;

        if (!allFiles.length) {
            showEmpty();
            return;
        }

        document.getElementById('dashboard-lightbox-loading').classList.add('d-none');
        document.getElementById('dashboard-lightbox-error').classList.add('d-none');
        document.getElementById('dashboard-lightbox-empty').classList.add('d-none');
        document.getElementById('dashboard-lightbox-content').classList.remove('d-none');

        bindPaginationClicks();
        renderPage();
    }

    function loadFromUrl(filesUrl, panel) {
        setLoading();
        return fetch(filesUrl, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Could not load image previews (' + response.status + ')');
                }
                return response.json();
            })
            .then(function (data) {
                showContent(data, panel);
                return data;
            })
            .catch(function (error) {
                showError(error.message || 'Could not load image previews.');
            });
    }

    function loadFromPanel() {
        var panel = document.getElementById('dashboard-lightbox-panel');
        if (!panel) {
            return;
        }
        var filesUrl = panel.getAttribute('data-files-url');
        if (!filesUrl) {
            return;
        }
        return loadFromUrl(filesUrl, panel);
    }

    function loadForFolder(folderId) {
        var panel = document.getElementById('dashboard-lightbox-panel');
        if (!panel) {
            return;
        }
        var urlBase = panel.getAttribute('data-api-path') || '/api/folders/';
        var url = urlBase + encodeURIComponent(folderId) + '/files';
        panel.setAttribute('data-files-url', url);
        panel.setAttribute('data-folder-id', String(folderId));
        return loadFromUrl(url, panel);
    }

    window.OspreyDashboardLightbox = {
        loadFromPanel: loadFromPanel,
        loadForFolder: loadForFolder
    };
}());
