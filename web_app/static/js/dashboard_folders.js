(function () {
    'use strict';

    var QC_BADGES = ['QC Passed', 'QC Failed', 'QC Pending'];
    var FILE_COUNT_RE = /^\d[\d,]* files$/i;
    var SKIP_CHIP_BADGES = /^MD5 Valid$/i;

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function parseBadges(badges) {
        if (!badges) {
            return [];
        }
        return badges.split(',').map(function (item) {
            return item.trim();
        }).filter(Boolean);
    }

    function fileCountFromBadges(badges) {
        var match = (badges || '').match(/(\d[\d,]*)\s+files/i);
        return match ? match[1] + ' files' : null;
    }

    function isInDams(folder) {
        return parseBadges(folder.badges).indexOf('Delivered to DAMS') !== -1;
    }

    function isUnavailable(folder) {
        if (folder.status !== 0) {
            return true;
        }
        if (folder.previews && folder.previews !== 0) {
            return true;
        }
        return parseBadges(folder.badges).some(function (badge) {
            return badge.indexOf('Folder under verification') !== -1;
        });
    }

    function normalizeFolder(folder) {
        var badgeList = parseBadges(folder.badges);
        return {
            folder_id: folder.folder_id,
            folder: folder.folder,
            badges: folder.badges,
            badgeList: badgeList,
            file_errors: folder.file_errors,
            qc_status: folder.qc_status,
            status: folder.status,
            previews: folder.previews,
            capture_date: folder.capture_date,
            section: isInDams(folder) ? 'dams' : 'active',
            fileCount: fileCountFromBadges(folder.badges) ||
                (folder.no_files ? String(folder.no_files) + ' files' : null),
            unavailable: isUnavailable(folder)
        };
    }

    function extraBadges(badgeList) {
        return badgeList.filter(function (badge) {
            if (SKIP_CHIP_BADGES.test(badge)) {
                return false;
            }
            if (QC_BADGES.indexOf(badge) !== -1) {
                return false;
            }
            if (FILE_COUNT_RE.test(badge)) {
                return false;
            }
            if (badge === 'Delivered to DAMS') {
                return false;
            }
            return true;
        });
    }

    function dotClass(folder, selectedFolderId) {
        if (folder.unavailable) {
            return 'dashboard-folder-dot-unavailable';
        }
        if (String(folder.folder_id) === String(selectedFolderId)) {
            return 'dashboard-folder-dot-selected';
        }
        if (folder.file_errors === 1 || folder.qc_status === 'QC Failed') {
            return 'dashboard-folder-dot-error';
        }
        if (folder.qc_status === 'QC Pending') {
            return 'dashboard-folder-dot-pending';
        }
        return 'dashboard-folder-dot-ok';
    }

    function qcBadgeClass(qcStatus) {
        if (qcStatus === 'QC Passed') {
            return 'text-bg-success';
        }
        if (qcStatus === 'QC Failed') {
            return 'text-bg-danger';
        }
        return 'text-bg-warning';
    }

    function extraBadgeClass(badge) {
        if (/error/i.test(badge)) {
            return 'text-bg-danger';
        }
        if (/Ready for DAMS/i.test(badge)) {
            return 'text-bg-secondary';
        }
        if (badge === 'Delivered to DAMS') {
            return 'text-bg-success';
        }
        return 'text-bg-light border';
    }

    function buildChipsHtml(folder) {
        var chips = [];

        if (folder.unavailable) {
            chips.push('<span class="badge text-bg-secondary">Not available</span>');
        } else {
            if (folder.fileCount) {
                chips.push('<span class="badge text-bg-primary">' + escapeHtml(folder.fileCount) + '</span>');
            }
            if (folder.file_errors === 1) {
                chips.push('<span class="badge text-bg-danger">Errors</span>');
            }
            if (folder.section === 'dams') {
                chips.push('<span class="badge text-bg-success">Delivered to DAMS</span>');
            }
            if (folder.qc_status) {
                chips.push('<span class="badge ' + qcBadgeClass(folder.qc_status) + '">' +
                    escapeHtml(folder.qc_status) + '</span>');
            }
        }

        extraBadges(folder.badgeList).forEach(function (badge) {
            chips.push('<span class="badge ' + extraBadgeClass(badge) + '">' + escapeHtml(badge) + '</span>');
        });

        return chips.join('');
    }

    function buildRowHtml(folder, projectAlias, selectedFolderId) {
        var slug = folder.folder.replace(/ /g, '_');
        var title = escapeHtml(folder.folder);
        var tooltip = folder.capture_date ?
            title + ' (' + escapeHtml(folder.capture_date) + ')' : title;
        var chips = buildChipsHtml(folder);
        var inner =
            '<span class="dashboard-folder-dot ' + dotClass(folder, selectedFolderId) + '" aria-hidden="true"></span>' +
            '<span class="dashboard-folder-name" title="' + tooltip + '">' + title + '</span>' +
            '<span class="dashboard-folder-chips">' + chips + '</span>';

        if (folder.unavailable) {
            return '<div class="dashboard-folder-row unavailable" id="' + escapeHtml(slug) + '" ' +
                'data-folder-name="' + escapeHtml(folder.folder.toLowerCase()) + '" ' +
                'data-folder-section="' + folder.section + '">' + inner + '</div>';
        }

        var href = '/dashboard/' + encodeURIComponent(projectAlias) + '/' + folder.folder_id + '/';
        var selected = String(folder.folder_id) === String(selectedFolderId);
        return '<a href="' + href + '" class="dashboard-folder-row' + (selected ? ' selected' : '') + '" ' +
            'id="' + escapeHtml(slug) + '" ' +
            'data-folder-name="' + escapeHtml(folder.folder.toLowerCase()) + '" ' +
            'data-folder-section="' + folder.section + '"' +
            (selected ? ' aria-current="true"' : '') + '>' + inner + '</a>';
    }

    function matchesFilter(folder, filterMode) {
        if (filterMode === 'ok') {
            return !folder.unavailable &&
                folder.file_errors !== 1 &&
                folder.qc_status === 'QC Passed' &&
                folder.section !== 'dams';
        }
        if (filterMode === 'errors') {
            return folder.file_errors === 1;
        }
        if (filterMode === 'qc') {
            return folder.qc_status === 'QC Failed';
        }
        if (filterMode === 'qc_pending') {
            return folder.qc_status === 'QC Pending';
        }
        if (filterMode === 'dams') {
            return folder.section === 'dams';
        }
        if (filterMode === 'unavailable') {
            return folder.unavailable;
        }
        return true;
    }

    var FILTER_BUTTON_LABELS = {
        all: 'All',
        ok: 'OK',
        errors: 'Errors',
        qc: 'QC Failed',
        qc_pending: 'QC Pending',
        dams: 'In DAMS',
        unavailable: 'Unavailable'
    };

    function initDashboardFolders() {
        var panel = document.getElementById('dashboard-folder-panel');
        if (!panel) {
            return;
        }

        var foldersUrl = panel.getAttribute('data-folders-url');
        var projectAlias = panel.getAttribute('data-project-alias');
        var selectedFolderId = panel.getAttribute('data-selected-folder-id') || '';
        var searchInput = document.getElementById('folder-search');
        var emptyMsg = document.getElementById('folder-search-empty');
        var loadingEl = document.getElementById('folder-list-loading');
        var errorEl = document.getElementById('folder-list-error');
        var controlsEl = document.getElementById('folder-list-controls');
        var desktopEl = document.getElementById('folder-list-desktop');
        var mobileSelect = document.getElementById('folder-select-mobile');
        var countEl = document.getElementById('folder-total-count');
        var filterButtons = panel.querySelectorAll('[data-folder-filter]');

        var allFolders = [];
        var filterMode = 'ok';

        function setLoading(isLoading) {
            if (loadingEl) {
                loadingEl.classList.toggle('d-none', !isLoading);
            }
            if (controlsEl) {
                controlsEl.classList.toggle('d-none', isLoading);
            }
            if (desktopEl) {
                desktopEl.classList.toggle('d-none', isLoading);
            }
        }

        function setError(message) {
            if (errorEl) {
                errorEl.textContent = message;
                errorEl.classList.remove('d-none');
            }
        }

        function countForFilter(mode) {
            if (mode === 'all') {
                return allFolders.length;
            }
            return allFolders.filter(function (folder) {
                return matchesFilter(folder, mode);
            }).length;
        }

        function updateFilterButtons() {
            filterButtons.forEach(function (btn) {
                var mode = btn.getAttribute('data-folder-filter') || 'all';
                var label = FILTER_BUTTON_LABELS[mode] || mode;
                btn.textContent = label + ' - ' + countForFilter(mode);
                var isActive = mode === filterMode;
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
        }

        function visibleFolders() {
            var query = searchInput ? searchInput.value.trim().toLowerCase() : '';
            return allFolders.filter(function (folder) {
                var matchesSearch = !query || folder.folder.toLowerCase().indexOf(query) !== -1;
                var matchesChip = matchesFilter(folder, filterMode);
                return matchesSearch && matchesChip;
            });
        }

        function renderMobileSelect(folders) {
            if (!mobileSelect) {
                return;
            }

            var html = '<option value="" disabled' +
                (selectedFolderId ? '' : ' selected') + '>Select a folder…</option>';

            folders.forEach(function (folder) {
                if (folder.unavailable) {
                    html += '<option disabled>' + escapeHtml(folder.folder) + ' (not available)</option>';
                    return;
                }
                var href = '/dashboard/' + encodeURIComponent(projectAlias) + '/' + folder.folder_id + '/';
                var selected = String(folder.folder_id) === String(selectedFolderId) ? ' selected' : '';
                var suffix = folder.fileCount ? ' (' + escapeHtml(folder.fileCount) + ')' : '';
                html += '<option value="' + href + '"' + selected + '>' +
                    escapeHtml(folder.folder) + suffix + '</option>';
            });

            mobileSelect.innerHTML = html;
        }

        function updateSelectedFolder(folderId) {
            selectedFolderId = String(folderId);
            panel.setAttribute('data-selected-folder-id', selectedFolderId);
            if (desktopEl) {
                desktopEl.querySelectorAll('.dashboard-folder-row').forEach(function (row) {
                    var isSelected = row.getAttribute('href') &&
                        row.getAttribute('href').endsWith('/' + selectedFolderId + '/');
                    row.classList.toggle('selected', isSelected);
                    if (isSelected) {
                        row.setAttribute('aria-current', 'true');
                    } else {
                        row.removeAttribute('aria-current');
                    }
                    var dot = row.querySelector('.dashboard-folder-dot');
                    if (dot) {
                        dot.className = 'dashboard-folder-dot ' +
                            dotClass(allFolders.find(function (f) {
                                return String(f.folder_id) === selectedFolderId;
                            }) || { folder_id: folderId }, selectedFolderId);
                    }
                });
            }
            if (mobileSelect) {
                var href = '/dashboard/' + encodeURIComponent(projectAlias) + '/' + selectedFolderId + '/';
                mobileSelect.value = href;
            }
        }

        function onFolderNavigate(event, href, folderId) {
            var hasFilesLoader = document.getElementById('dashboard-files-panel') && window.OspreyDashboardFiles;
            var hasQcLoader = document.getElementById('dashboard-qc-panel') && window.OspreyDashboardQc;
            var hasLightboxLoader = document.getElementById('dashboard-lightbox-panel') && window.OspreyDashboardLightbox;
            var hasPostprodLoader = document.getElementById('dashboard-postprod-panel') && window.OspreyDashboardPostprocessing;
            if (!hasFilesLoader && !hasQcLoader && !hasLightboxLoader && !hasPostprodLoader) {
                return;
            }
            event.preventDefault();
            updateSelectedFolder(folderId);
            if (window.history && window.history.pushState) {
                window.history.pushState({ folderId: folderId }, '', href);
            }
            if (hasFilesLoader) {
                window.OspreyDashboardFiles.loadForFolder(folderId);
            }
            if (hasQcLoader) {
                window.OspreyDashboardQc.loadForFolder(folderId);
            }
            if (hasLightboxLoader) {
                window.OspreyDashboardLightbox.loadForFolder(folderId);
            }
            if (hasPostprodLoader) {
                window.OspreyDashboardPostprocessing.loadForFolder(folderId);
            }
        }

        var folderNavBound = false;

        function bindFolderNavigation() {
            if (!desktopEl || folderNavBound) {
                return;
            }
            folderNavBound = true;
            desktopEl.addEventListener('click', function (event) {
                var row = event.target.closest('a.dashboard-folder-row');
                if (!row || !row.getAttribute('href')) {
                    return;
                }
                var match = row.getAttribute('href').match(/\/([^/]+)\/?$/);
                if (!match) {
                    return;
                }
                onFolderNavigate(event, row.getAttribute('href'), match[1]);
            });
        }

        function renderDesktopList(folders) {
            if (!desktopEl) {
                return;
            }

            if (!folders.length) {
                desktopEl.innerHTML = '';
                return;
            }

            var html = '<div class="dashboard-folder-list list-group shadow-sm">';
            folders.forEach(function (folder) {
                html += buildRowHtml(folder, projectAlias, selectedFolderId);
            });
            html += '</div>';
            desktopEl.innerHTML = html;
        }

        function render() {
            var folders = visibleFolders();
            renderDesktopList(folders);
            bindFolderNavigation();
            renderMobileSelect(folders);

            if (countEl) {
                countEl.textContent = allFolders.length;
            }

            updateFilterButtons();

            if (emptyMsg) {
                var hasCriteria = (searchInput && searchInput.value.trim()) || filterMode !== 'all';
                emptyMsg.classList.toggle('d-none', folders.length > 0 || !hasCriteria);
            }
        }

        filterButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                var mode = button.getAttribute('data-folder-filter') || 'all';
                if (mode !== 'all' && filterMode === mode) {
                    filterMode = 'all';
                } else {
                    filterMode = mode;
                }
                render();
            });
        });

        if (searchInput) {
            searchInput.addEventListener('input', render);
        }

        if (mobileSelect) {
            mobileSelect.addEventListener('change', function () {
                if (!this.value) {
                    return;
                }
                var hasFilesLoader = document.getElementById('dashboard-files-panel') && window.OspreyDashboardFiles;
                var hasQcLoader = document.getElementById('dashboard-qc-panel') && window.OspreyDashboardQc;
                var hasLightboxLoader = document.getElementById('dashboard-lightbox-panel') && window.OspreyDashboardLightbox;
                var hasPostprodLoader = document.getElementById('dashboard-postprod-panel') && window.OspreyDashboardPostprocessing;
                if (hasFilesLoader || hasQcLoader || hasLightboxLoader || hasPostprodLoader) {
                    var match = this.value.match(/\/([^/]+)\/?$/);
                    if (match) {
                        updateSelectedFolder(match[1]);
                        if (window.history && window.history.pushState) {
                            window.history.pushState({ folderId: match[1] }, '', this.value);
                        }
                        if (hasFilesLoader) {
                            window.OspreyDashboardFiles.loadForFolder(match[1]);
                        }
                        if (hasQcLoader) {
                            window.OspreyDashboardQc.loadForFolder(match[1]);
                        }
                        if (hasLightboxLoader) {
                            window.OspreyDashboardLightbox.loadForFolder(match[1]);
                        }
                        if (hasPostprodLoader) {
                            window.OspreyDashboardPostprocessing.loadForFolder(match[1]);
                        }
                        return;
                    }
                }
                window.location.href = this.value;
            });
        }

        setLoading(true);
        fetch(foldersUrl, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Could not load folders (' + response.status + ')');
                }
                return response.json();
            })
            .then(function (data) {
                allFolders = (data.folders || []).map(normalizeFolder);
                setLoading(false);
                render();
            })
            .catch(function (error) {
                setLoading(false);
                setError(error.message || 'Could not load folders.');
            });
    }

    document.addEventListener('DOMContentLoaded', initDashboardFolders);
})();
