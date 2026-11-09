(function () {
    'use strict';

    var PAGE_SIZE = 25;
    var allFiles = [];
    var lightboxFilter = 'all';
    var currentPage = 1;
    var currentConfig = {};
    var controlsBound = false;
    // JSON of the last payload drawn; a background refresh with the same data
    // leaves the grid alone.
    var lastPayloadKey = null;

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

    // 'failed' if any file check failed, 'pending' if any is still pending.
    function fileStatus(file) {
        var checks = file.file_checks || [];
        var pending = false;
        for (var i = 0; i < checks.length; i++) {
            if (checks[i].check_results === 'Failed') {
                return 'failed';
            }
            if (checks[i].check_results === 'Pending') {
                pending = true;
            }
        }
        return pending ? 'pending' : 'ok';
    }

    function filteredFiles() {
        if (lightboxFilter === 'failed') {
            return allFiles.filter(function (file) {
                return fileStatus(file) === 'failed';
            });
        }
        return allFiles;
    }

    function fileCardHtml(file, transcription, appRoot, folderId) {
        var detailPath = transcription ?
            appRoot + '/file_transcription/' + file.file_id + '/' :
            appRoot + '/file/' + file.file_id + '/';
        var status = fileStatus(file);
        var statusHtml = '';
        if (status === 'failed') {
            statusHtml = '<span class="badge text-bg-danger">Failed checks</span>';
        } else if (status === 'pending') {
            statusHtml = '<span class="badge text-bg-light border">Checks pending</span>';
        }
        // The file name is the link text, so the thumbnail itself is decorative.
        return '<a class="dashboard-lightbox-card' + (status === 'failed' ? ' is-failed' : '') + '" ' +
            'href="' + detailPath + '" title="Details of the file ' + escapeHtml(file.file_name) + '">' +
            '<span class="dashboard-lightbox-thumb">' +
                '<img src="' + previewSrc(file, transcription, appRoot, folderId) + '" alt="" ' +
                'width="160" height="160" loading="lazy" decoding="async">' +
            '</span>' +
            '<span class="dashboard-lightbox-name">' + escapeHtml(file.file_name) + '</span>' +
            statusHtml +
            '</a>';
    }

    function pageItem(label, targetPage, enabled, active) {
        if (!enabled) {
            return '<li class="page-item disabled"><span class="page-link" aria-disabled="true">' + label + '</span></li>';
        }
        return '<li class="page-item' + (active ? ' active' : '') + '">' +
            '<a class="page-link" href="#" data-lightbox-page="' + targetPage + '"' +
            (active ? ' aria-current="page"' : '') + '>' + label + '</a></li>';
    }

    function buildPaginationHtml(page, totalPages) {
        if (totalPages <= 1) {
            return '';
        }
        var html = '<ul class="pagination pagination-sm mb-0">';
        html += pageItem('Previous', page - 1, page > 1);

        var start = Math.max(1, page - 3);
        var end = Math.min(totalPages, page + 3);

        if (start > 1) {
            html += pageItem('1', 1, true);
            if (start > 2) {
                html += pageItem('&hellip;', 0, false);
            }
        }
        for (var i = start; i <= end; i++) {
            html += pageItem(String(i), i, true, i === page);
        }
        if (end < totalPages) {
            if (end < totalPages - 1) {
                html += pageItem('&hellip;', 0, false);
            }
            html += pageItem(String(totalPages), totalPages, true);
        }

        html += pageItem('Next', page + 1, page < totalPages);
        html += '</ul>';
        return html;
    }

    function updateFilterButtons() {
        var counts = {
            all: allFiles.length,
            failed: allFiles.filter(function (file) {
                return fileStatus(file) === 'failed';
            }).length
        };
        document.querySelectorAll('[data-lightbox-filter]').forEach(function (btn) {
            var mode = btn.getAttribute('data-lightbox-filter');
            var isActive = mode === lightboxFilter;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            var countEl = btn.querySelector('[data-count-for]');
            if (countEl) {
                countEl.textContent = counts[mode];
            }
        });
    }

    function renderPage() {
        var files = filteredFiles();
        var totalPages = Math.max(1, Math.ceil(files.length / PAGE_SIZE));
        if (currentPage > totalPages) {
            currentPage = totalPages;
        }
        var start = (currentPage - 1) * PAGE_SIZE;
        var pageFiles = files.slice(start, start + PAGE_SIZE);

        var gridEl = document.getElementById('lightbox-grid');
        if (pageFiles.length) {
            gridEl.innerHTML = pageFiles.map(function (file) {
                return fileCardHtml(file, currentConfig.transcription, currentConfig.appRoot, currentConfig.folderId);
            }).join('');
        } else {
            gridEl.innerHTML = '<p class="text-muted mb-0">No files with failed checks in this folder.</p>';
        }

        var paginationHtml = buildPaginationHtml(currentPage, totalPages);
        document.getElementById('dashboard-lightbox-pagination-top').innerHTML = paginationHtml;
        document.getElementById('dashboard-lightbox-pagination-bottom').innerHTML = paginationHtml;
        updateFilterButtons();
    }

    // After paging from the bottom links, bring the top of the grid back into view.
    function scrollToGridTop() {
        var panel = document.getElementById('dashboard-lightbox-panel');
        if (panel && panel.getBoundingClientRect().top < 0) {
            panel.scrollIntoView({ block: 'start' });
        }
    }

    function bindControls() {
        if (controlsBound) {
            return;
        }
        controlsBound = true;
        document.getElementById('dashboard-lightbox-content').addEventListener('click', function (event) {
            var link = event.target.closest('[data-lightbox-page]');
            if (link) {
                event.preventDefault();
                currentPage = parseInt(link.getAttribute('data-lightbox-page'), 10);
                renderPage();
                scrollToGridTop();
                return;
            }
            var filterBtn = event.target.closest('[data-lightbox-filter]');
            if (filterBtn) {
                lightboxFilter = filterBtn.getAttribute('data-lightbox-filter');
                currentPage = 1;
                renderPage();
            }
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

    // silent: background refresh - keep the current filter and page.
    function showContent(data, panel, silent) {
        var payloadKey = JSON.stringify(data);
        if (silent && payloadKey === lastPayloadKey) {
            return;
        }
        lastPayloadKey = payloadKey;

        currentConfig = panelConfig(panel);
        allFiles = (data.files || []).slice();
        if (!silent) {
            currentPage = 1;
            lightboxFilter = 'all';
        }

        var nameEl = document.getElementById('dashboard-lightbox-folder-name');
        if (nameEl) {
            nameEl.textContent = data.folder || '';
        }
        if (data.last_updated) {
            var lastUpdatedEl = document.getElementById('dashboard-folder-last-updated');
            if (lastUpdatedEl) {
                lastUpdatedEl.textContent = data.last_updated;
            }
        }

        if (!allFiles.length) {
            showEmpty();
            return;
        }

        document.getElementById('dashboard-lightbox-loading').classList.add('d-none');
        document.getElementById('dashboard-lightbox-error').classList.add('d-none');
        document.getElementById('dashboard-lightbox-empty').classList.add('d-none');
        document.getElementById('dashboard-lightbox-content').classList.remove('d-none');

        bindControls();
        renderPage();
    }

    function loadFromUrl(filesUrl, panel, silent) {
        // See dashboard_table_panel.js loadFromUrl for why this guard is needed:
        // it drops responses that arrive after a newer folder has been requested.
        var requestFolderId = panel.getAttribute('data-folder-id');
        if (!silent) {
            setLoading();
        }
        return fetch(filesUrl, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Could not load image previews (' + response.status + ')');
                }
                return response.json();
            })
            .then(function (data) {
                if (panel.getAttribute('data-folder-id') !== requestFolderId) {
                    return data;
                }
                showContent(data, panel, silent);
                return data;
            })
            .catch(function (error) {
                if (panel.getAttribute('data-folder-id') !== requestFolderId) {
                    return;
                }
                if (silent) {
                    throw error;
                }
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
        lastPayloadKey = null;
        return loadFromUrl(url, panel);
    }

    function refresh() {
        var panel = document.getElementById('dashboard-lightbox-panel');
        if (!panel || !panel.getAttribute('data-files-url')) {
            return;
        }
        return loadFromUrl(panel.getAttribute('data-files-url'), panel, true);
    }

    window.OspreyDashboardLightbox = {
        loadFromPanel: loadFromPanel,
        loadForFolder: loadForFolder,
        refresh: refresh
    };
}());
