(function () {
    'use strict';

    var QC_BADGES = ['QC Passed', 'QC Failed', 'QC Pending'];
    var TRANSCRIPTION_QC_BADGE_RE = /^Transcription QC /i;
    var FILE_COUNT_RE = /^\d[\d,]* files?$/i;
    var SKIP_CHIP_BADGES = /^MD5 Valid$/i;
    var PREVIEW_TYPE_BADGES = /^(DZI|IIIF)$/i;

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
        var match = (badges || '').match(/(\d[\d,]*)\s+files?\b/i);
        if (!match) {
            return null;
        }
        var count = match[1];
        return count + (count === '1' ? ' file' : ' files');
    }

    function isInDams(folder) {
        return parseBadges(folder.badges).indexOf('Delivered to DAMS') !== -1;
    }

    function isUnavailable(folder) {
        // A folder-level processing error (status 1, e.g. an extraneous file)
        // is a real error, not "still processing" — keep it out of the
        // generic unavailable bucket so it gets error styling instead.
        if (folder.status === 1) {
            return false;
        }
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
            transcriptionQcBadges: transcriptionQcBadgesFromList(badgeList),
            file_errors: folder.file_errors,
            hasFolderError: folder.status === 1,
            qc_status: folder.qc_status,
            status: folder.status,
            previews: folder.previews,
            preview_type: folder.preview_type,
            capture_date: folder.capture_date,
            section: isInDams(folder) ? 'dams' : 'active',
            fileCount: fileCountFromBadges(folder.badges) ||
                (folder.no_files ? String(folder.no_files) + (Number(folder.no_files) === 1 ? ' file' : ' files') : null),
            unavailable: isUnavailable(folder),
            // Only sent for transcription projects (folders.list_for_project).
            hasTranscriptions: Number(folder.has_transcriptions) === 1
        };
    }

    function transcriptionQcBadgesFromList(badgeList) {
        return badgeList.filter(function (badge) {
            return TRANSCRIPTION_QC_BADGE_RE.test(badge);
        });
    }

    function hasTranscriptionQcFailed(folder) {
        if (!folder.hasTranscriptions) {
            return false;
        }
        return (folder.transcriptionQcBadges || []).some(function (badge) {
            return /Failed/i.test(badge);
        });
    }

    function hasTranscriptionQcPassed(folder) {
        if (!folder.hasTranscriptions || folder.unavailable || hasTranscriptionQcFailed(folder)) {
            return false;
        }
        return (folder.transcriptionQcBadges || []).some(function (badge) {
            return /Passed/i.test(badge);
        });
    }

    function hasTranscriptionQcPending(folder) {
        return folder.hasTranscriptions && !folder.unavailable &&
            (folder.transcriptionQcBadges || []).length === 0;
    }

    function extraBadges(badgeList) {
        return badgeList.filter(function (badge) {
            if (TRANSCRIPTION_QC_BADGE_RE.test(badge)) {
                return false;
            }
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
            if (PREVIEW_TYPE_BADGES.test(badge)) {
                return false;
            }
            return true;
        });
    }

    function dotClass(folder, qcEnabled) {
        if (folder.hasFolderError) {
            return 'dashboard-folder-dot-error';
        }
        if (folder.unavailable) {
            return 'dashboard-folder-dot-unavailable';
        }
        if (folder.file_errors === 1) {
            return 'dashboard-folder-dot-error';
        }
        if (qcEnabled) {
            if (folder.qc_status === 'QC Failed' || hasTranscriptionQcFailed(folder)) {
                return 'dashboard-folder-dot-error';
            }
            if (folder.qc_status === 'QC Pending') {
                return 'dashboard-folder-dot-pending';
            }
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

    function transcriptionQcBadgeClass(badge) {
        if (/Failed/i.test(badge)) {
            return 'text-bg-danger';
        }
        if (/Passed/i.test(badge)) {
            return 'text-bg-success';
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

    function buildChipsHtml(folder, qcEnabled) {
        var chips = [];

        if (folder.hasFolderError) {
            chips.push('<span class="badge text-bg-danger">Folder Error</span>');
        } else if (folder.unavailable) {
            chips.push('<span class="badge text-bg-secondary">Not available</span>');
        } else {
            if (folder.fileCount) {
                chips.push('<span class="badge text-bg-primary">' + escapeHtml(folder.fileCount) + '</span>');
            }
            if (folder.section === 'dams') {
                chips.push('<span class="badge text-bg-success">Delivered to DAMS</span>');
            }
            if (qcEnabled && folder.qc_status &&
                !(folder.file_errors === 1 && folder.qc_status === 'QC Pending')) {
                chips.push('<span class="badge ' + qcBadgeClass(folder.qc_status) + '">' +
                    escapeHtml(folder.qc_status) + '</span>');
            }
            if (qcEnabled) {
                (folder.transcriptionQcBadges || []).forEach(function (badge) {
                    chips.push('<span class="badge ' + transcriptionQcBadgeClass(badge) + '">' +
                        escapeHtml(badge) + '</span>');
                });
            }
            if (folder.preview_type === 'dzi') {
                chips.push('<span class="badge text-bg-info" title="Preview type: DZI">DZI</span>');
            } else if (folder.preview_type === 'iiif') {
                chips.push('<span class="badge text-bg-primary" title="Preview type: IIIF">IIIF</span>');
            }
        }

        extraBadges(folder.badgeList).forEach(function (badge) {
            var badgeClass = folder.hasFolderError ? 'text-bg-danger' : extraBadgeClass(badge);
            chips.push('<span class="badge ' + badgeClass + '">' + escapeHtml(badge) + '</span>');
        });

        return chips.join('');
    }

    function buildRowHtml(folder, projectAlias, selectedFolderId, qcEnabled) {
        var slug = folder.folder.replace(/ /g, '_');
        var title = escapeHtml(folder.folder);
        var tooltip = folder.capture_date ?
            title + ' (' + escapeHtml(folder.capture_date) + ')' : title;
        var chips = buildChipsHtml(folder, qcEnabled);
        var inner =
            '<span class="dashboard-folder-dot ' + dotClass(folder, qcEnabled) + '" aria-hidden="true"></span>' +
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

    function hasErrors(folder) {
        return folder.file_errors === 1 || folder.hasFolderError;
    }

    // Folders someone should look at: errors, failed QC, or QC still to do.
    // Unavailable folders are still processing and DAMS folders are done.
    function needsAttention(folder, qcEnabled) {
        if (folder.unavailable) {
            return false;
        }
        if (hasErrors(folder)) {
            return true;
        }
        if (!qcEnabled || folder.section === 'dams') {
            return false;
        }
        return folder.qc_status === 'QC Failed' ||
            folder.qc_status === 'QC Pending' ||
            hasTranscriptionQcFailed(folder);
    }

    function matchesFilter(folder, filterMode, qcEnabled) {
        if (filterMode === 'attention') {
            return needsAttention(folder, qcEnabled);
        }
        if (filterMode === 'ok') {
            if (!folder.unavailable &&
                !folder.hasFolderError &&
                folder.file_errors !== 1 &&
                folder.section !== 'dams') {
                if (!qcEnabled) {
                    return true;
                }
                return folder.qc_status === 'QC Passed' && !hasTranscriptionQcFailed(folder);
            }
            return false;
        }
        if (filterMode === 'errors') {
            return hasErrors(folder);
        }
        // Not tied to QC: shown in transcription projects even with QC off.
        if (filterMode === 'transcribed') {
            return folder.hasTranscriptions;
        }
        if (!qcEnabled && (
            filterMode === 'qc' ||
            filterMode === 'qc_pending' ||
            filterMode === 'transcription_qc' ||
            filterMode === 'transcription_qc_passed' ||
            filterMode === 'transcription_qc_pending'
        )) {
            return false;
        }
        if (filterMode === 'qc') {
            return folder.qc_status === 'QC Failed';
        }
        if (filterMode === 'qc_pending') {
            return folder.qc_status === 'QC Pending' && folder.file_errors !== 1 && !folder.hasFolderError;
        }
        if (filterMode === 'transcription_qc') {
            return hasTranscriptionQcFailed(folder);
        }
        if (filterMode === 'transcription_qc_passed') {
            return hasTranscriptionQcPassed(folder);
        }
        if (filterMode === 'transcription_qc_pending') {
            return hasTranscriptionQcPending(folder);
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
        attention: 'Needs attention',
        ok: 'OK',
        errors: 'Errors',
        qc: 'QC Failed',
        qc_pending: 'QC Pending',
        transcribed: 'Transcribed',
        transcription_qc: 'Transcription QC Failed',
        transcription_qc_passed: 'Transcription QC Passed',
        transcription_qc_pending: 'Transcription QC Pending',
        dams: 'In DAMS',
        unavailable: 'Unavailable'
    };

    // Background refresh: replaces the old "reload the page after 10 minutes
    // idle", which threw away scroll position, filters and table state.
    var REFRESH_INTERVAL_MS = 5 * 60 * 1000;
    var IDLE_BEFORE_REFRESH_MS = 60 * 1000;
    var STATUS_TICK_MS = 30 * 1000;

    // [panel element id, global loader]; only the panels for the active tab
    // exist in the DOM.
    var PANEL_MODULES = [
        ['dashboard-files-panel', 'OspreyDashboardFiles'],
        ['dashboard-qc-panel', 'OspreyDashboardQc'],
        ['dashboard-lightbox-panel', 'OspreyDashboardLightbox'],
        ['dashboard-postprod-panel', 'OspreyDashboardPostprocessing'],
        ['dashboard-transcription-qc-panel', 'OspreyDashboardTranscriptionQc'],
        ['dashboard-transcription-fill-panel', 'OspreyDashboardTranscriptionFill']
    ];

    function activePanelModules() {
        return PANEL_MODULES.filter(function (entry) {
            return document.getElementById(entry[0]) && window[entry[1]];
        }).map(function (entry) {
            return window[entry[1]];
        });
    }

    function storageGet(key) {
        try {
            return window.sessionStorage.getItem(key);
        } catch (e) {
            return null;
        }
    }

    function storageSet(key, value) {
        try {
            window.sessionStorage.setItem(key, value);
        } catch (e) {
            // Storage blocked (private mode etc.): the filter just isn't remembered.
        }
    }

    function updatedAgoText(ms) {
        var minutes = Math.floor(ms / 60000);
        if (minutes < 1) {
            return 'updated just now';
        }
        if (minutes < 60) {
            return 'updated ' + minutes + ' min ago';
        }
        return 'updated ' + Math.floor(minutes / 60) + ' h ago';
    }

    function initDashboardFolders() {
        var panel = document.getElementById('dashboard-folder-panel');
        if (!panel) {
            return;
        }

        var foldersUrl = panel.getAttribute('data-folders-url');
        var projectAlias = panel.getAttribute('data-project-alias');
        var selectedFolderId = panel.getAttribute('data-selected-folder-id') || '';
        var qcEnabled = panel.getAttribute('data-qc-enabled') !== '0';
        var searchInput = document.getElementById('folder-search');
        var emptyMsg = document.getElementById('folder-search-empty');
        var searchNote = document.getElementById('folder-search-note');
        var loadingEl = document.getElementById('folder-list-loading');
        var errorEl = document.getElementById('folder-list-error');
        var controlsEl = document.getElementById('folder-list-controls');
        var desktopEl = document.getElementById('folder-list-desktop');
        var mobileSelect = document.getElementById('folder-select-mobile');
        var countEl = document.getElementById('folder-total-count');
        var filtersEl = document.getElementById('folder-filters');
        var moreSelect = document.getElementById('folder-filter-more');
        var currentFilterEl = document.getElementById('folder-filter-current');
        var refreshStatusEl = document.getElementById('dashboard-refresh-status');
        var refreshBtn = document.getElementById('dashboard-refresh-btn');
        var filterButtons = panel.querySelectorAll('[data-folder-filter]');
        var filterStorageKey = 'osprey.dashboard.folderFilter.' + projectAlias;

        var allFolders = [];
        var filterMode = 'all';
        var lastRefreshAt = Date.now();
        var lastInteractionAt = Date.now();
        var lastRefreshFailed = false;
        var refreshing = false;

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

        function searchQuery() {
            return searchInput ? searchInput.value.trim().toLowerCase() : '';
        }

        function isSelected(folder) {
            return selectedFolderId !== '' && String(folder.folder_id) === String(selectedFolderId);
        }

        function countForFilter(mode) {
            if (mode === 'all') {
                return allFolders.length;
            }
            return allFolders.filter(function (folder) {
                return matchesFilter(folder, mode, qcEnabled);
            }).length;
        }

        function isValidFilter(mode) {
            if (!mode) {
                return false;
            }
            if (mode === 'all') {
                return true;
            }
            var selector = '[data-folder-filter="' + mode + '"]';
            var option = 'option[value="' + mode + '"]';
            return Boolean(panel.querySelector(selector) || (moreSelect && moreSelect.querySelector(option)));
        }

        // Remembered per project for this browser tab, so switching tabs or
        // reloading keeps the filter. First visit: show what needs attention.
        function initialFilter() {
            var saved = storageGet(filterStorageKey);
            if (isValidFilter(saved)) {
                return saved;
            }
            return countForFilter('attention') > 0 ? 'attention' : 'all';
        }

        function setFilter(mode) {
            filterMode = mode;
            storageSet(filterStorageKey, mode);
        }

        function visibleFolders() {
            var query = searchQuery();
            return allFolders.filter(function (folder) {
                if (query) {
                    // Search looks across every folder. The filter is kept
                    // (shown dimmed) and applies again once the search is cleared.
                    return folder.folder.toLowerCase().indexOf(query) !== -1;
                }
                // Keep the open folder in the list even if the filter would hide it.
                return isSelected(folder) || matchesFilter(folder, filterMode, qcEnabled);
            });
        }

        function updateFilterControls() {
            var searching = Boolean(searchQuery());

            filterButtons.forEach(function (btn) {
                var mode = btn.getAttribute('data-folder-filter') || 'all';
                var countBadge = btn.querySelector('[data-count-for]');
                if (countBadge) {
                    countBadge.textContent = countForFilter(mode);
                }
                var isActive = mode === filterMode;
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });

            if (moreSelect) {
                Array.prototype.forEach.call(moreSelect.querySelectorAll('option'), function (opt) {
                    if (opt.value) {
                        opt.textContent = (FILTER_BUTTON_LABELS[opt.value] || opt.value) +
                            ' (' + countForFilter(opt.value) + ')';
                    }
                });
                var inMore = Boolean(moreSelect.querySelector('option[value="' + filterMode + '"]'));
                moreSelect.value = inMore ? filterMode : '';
                moreSelect.classList.toggle('active', inMore);
            }

            if (filtersEl) {
                filtersEl.classList.toggle('is-paused', searching);
            }
            if (searchNote) {
                searchNote.classList.toggle('d-none', !searching);
            }
            if (currentFilterEl) {
                currentFilterEl.textContent = (FILTER_BUTTON_LABELS[filterMode] || filterMode) +
                    (searching ? ' (paused while searching)' : '');
            }
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
                var selected = isSelected(folder) ? ' selected' : '';
                var suffix = folder.fileCount ? ' (' + escapeHtml(folder.fileCount) + ')' : '';
                html += '<option value="' + href + '"' + selected + '>' +
                    escapeHtml(folder.folder) + suffix + '</option>';
            });

            mobileSelect.innerHTML = html;
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
                html += buildRowHtml(folder, projectAlias, selectedFolderId, qcEnabled);
            });
            html += '</div>';
            desktopEl.innerHTML = html;
        }

        // Scroll the folder list (not the page) so the open folder is visible.
        function scrollSelectedIntoView() {
            if (!desktopEl) {
                return;
            }
            var row = desktopEl.querySelector('.dashboard-folder-row.selected');
            if (!row) {
                return;
            }
            var top = row.offsetTop;
            var bottom = top + row.offsetHeight;
            if (top < desktopEl.scrollTop || bottom > desktopEl.scrollTop + desktopEl.clientHeight) {
                desktopEl.scrollTop = Math.max(0, top - desktopEl.clientHeight / 3);
            }
        }

        // keepPosition: re-render in place (refresh / folder switch) instead of
        // starting the list from the top (filter or search change).
        function render(keepPosition) {
            var folders = visibleFolders();
            var scrollTop = desktopEl ? desktopEl.scrollTop : 0;
            var focusedHref = null;
            if (desktopEl && desktopEl.contains(document.activeElement)) {
                focusedHref = document.activeElement.getAttribute('href');
            }

            renderDesktopList(folders);
            renderMobileSelect(folders);

            if (desktopEl) {
                desktopEl.scrollTop = keepPosition ? scrollTop : 0;
                if (focusedHref) {
                    var again = desktopEl.querySelector('a[href="' + focusedHref.replace(/"/g, '\\"') + '"]');
                    if (again) {
                        again.focus({ preventScroll: true });
                    }
                }
            }

            if (countEl) {
                countEl.textContent = allFolders.length;
            }

            updateFilterControls();

            if (emptyMsg) {
                if (!allFolders.length) {
                    emptyMsg.textContent = 'This project has no folders yet.';
                } else if (searchQuery()) {
                    emptyMsg.textContent = 'No folders match your search.';
                } else {
                    emptyMsg.textContent = 'No folders match this filter.';
                }
                emptyMsg.classList.toggle('d-none', folders.length > 0);
            }
        }

        function updateMainPanelBadges(folderId) {
            var badgesEl = document.getElementById('dashboard-folder-badges');
            if (!badgesEl) {
                return;
            }
            var folder = allFolders.find(function (f) {
                return String(f.folder_id) === String(folderId);
            });
            badgesEl.innerHTML = folder ? buildChipsHtml(folder, qcEnabled) : '';
        }

        function updateSelectedFolder(folderId) {
            selectedFolderId = String(folderId);
            panel.setAttribute('data-selected-folder-id', selectedFolderId);
            render(true);
            updateMainPanelBadges(selectedFolderId);
        }

        function getActiveDashboardTab() {
            var active = document.querySelector('.dashboard-tabs a.nav-link.active[data-tab]');
            return active ? active.getAttribute('data-tab') : 'filechecks';
        }

        function folderDashboardUrl(folderId, tab) {
            var url = '/dashboard/' + encodeURIComponent(projectAlias) + '/' + folderId + '/';
            if (tab && tab !== 'filechecks') {
                url += encodeURIComponent(tab) + '/';
            }
            return url;
        }

        function updateDashboardTabLinks(folderId) {
            var links = document.querySelectorAll('.dashboard-tabs a.nav-link[data-tab]');
            Array.prototype.forEach.call(links, function (link) {
                var tab = link.getAttribute('data-tab');
                if (link.classList.contains('active')) {
                    link.setAttribute('href', '#');
                } else {
                    link.setAttribute('href', folderDashboardUrl(folderId, tab));
                }
            });
        }

        function loadPanelsForFolder(folderId) {
            activePanelModules().forEach(function (mod) {
                mod.loadForFolder(folderId);
            });
        }

        function navigateToFolder(folderId) {
            updateSelectedFolder(folderId);
            updateDashboardTabLinks(folderId);
            var navigateUrl = folderDashboardUrl(folderId, getActiveDashboardTab());
            if (window.history && window.history.pushState) {
                window.history.pushState({ folderId: folderId }, '', navigateUrl);
            }
            loadPanelsForFolder(folderId);
        }

        if (desktopEl) {
            desktopEl.addEventListener('click', function (event) {
                var row = event.target.closest('a.dashboard-folder-row');
                if (!row || !row.getAttribute('href') || !activePanelModules().length) {
                    return;
                }
                var match = row.getAttribute('href').match(/\/([^/]+)\/?$/);
                if (!match) {
                    return;
                }
                event.preventDefault();
                navigateToFolder(match[1]);
            });
        }

        function updateRefreshStatus() {
            if (!refreshStatusEl) {
                return;
            }
            refreshStatusEl.textContent = updatedAgoText(Date.now() - lastRefreshAt) +
                (lastRefreshFailed ? ' (last refresh failed)' : '');
        }

        function fetchFolders() {
            return fetch(foldersUrl, { credentials: 'same-origin' })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('Could not load folders (' + response.status + ')');
                    }
                    return response.json();
                })
                .then(function (data) {
                    return (data.folders || []).map(normalizeFolder);
                });
        }

        // Re-fetch the folder list and the open folder's panels without a page
        // reload. Each panel keeps its own state (filters, table page, open
        // accordions) and skips the redraw when nothing changed.
        function refreshAll() {
            if (refreshing) {
                return;
            }
            refreshing = true;
            if (refreshBtn) {
                refreshBtn.classList.add('is-refreshing');
                refreshBtn.disabled = true;
            }

            var failed = false;
            var jobs = [fetchFolders().then(function (folders) {
                allFolders = folders;
                render(true);
                if (selectedFolderId) {
                    updateMainPanelBadges(selectedFolderId);
                }
            })];
            if (selectedFolderId) {
                activePanelModules().forEach(function (mod) {
                    if (mod.refresh) {
                        jobs.push(Promise.resolve(mod.refresh()));
                    }
                });
            }

            Promise.all(jobs.map(function (job) {
                return job.catch(function () {
                    failed = true;
                });
            })).then(function () {
                refreshing = false;
                lastRefreshFailed = failed;
                if (!failed) {
                    lastRefreshAt = Date.now();
                }
                if (refreshBtn) {
                    refreshBtn.classList.remove('is-refreshing');
                    refreshBtn.disabled = false;
                }
                updateRefreshStatus();
            });
        }

        filterButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                var mode = button.getAttribute('data-folder-filter') || 'all';
                if (searchQuery()) {
                    // Picking a filter while searching means "use this filter now".
                    searchInput.value = '';
                    setFilter(mode);
                } else if (mode !== 'all' && filterMode === mode) {
                    setFilter('all');
                } else {
                    setFilter(mode);
                }
                render(false);
            });
        });

        if (moreSelect) {
            moreSelect.addEventListener('change', function () {
                if (searchInput) {
                    searchInput.value = '';
                }
                setFilter(this.value || 'all');
                render(false);
            });
        }

        if (searchInput) {
            searchInput.addEventListener('input', function () {
                render(false);
            });
        }

        if (mobileSelect) {
            mobileSelect.addEventListener('change', function () {
                if (!this.value) {
                    return;
                }
                if (activePanelModules().length) {
                    var match = this.value.match(/\/([^/]+)\/?$/);
                    if (match) {
                        navigateToFolder(match[1]);
                        return;
                    }
                }
                window.location.href = this.value;
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener('click', refreshAll);
        }

        // Browser Back/Forward after a soft folder switch: the URL and history
        // state move, but nothing else does unless we reload the panel data too.
        window.addEventListener('popstate', function (event) {
            var folderId = event.state && event.state.folderId;
            if (!folderId) {
                // No folderId on this history entry (e.g. the page's original
                // load) - reload so the page matches the URL we've landed on.
                window.location.reload();
                return;
            }
            if (!activePanelModules().length) {
                return;
            }
            updateSelectedFolder(folderId);
            scrollSelectedIntoView();
            updateDashboardTabLinks(folderId);
            loadPanelsForFolder(folderId);
        });

        ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach(function (eventName) {
            document.addEventListener(eventName, function () {
                lastInteractionAt = Date.now();
            }, { passive: true, capture: true });
        });

        // Refresh only while the tab is visible and the user has paused, so
        // nothing shifts under someone who is reading or typing.
        window.setInterval(function () {
            updateRefreshStatus();
            if (document.hidden) {
                return;
            }
            var now = Date.now();
            if (now - lastRefreshAt >= REFRESH_INTERVAL_MS && now - lastInteractionAt >= IDLE_BEFORE_REFRESH_MS) {
                refreshAll();
            }
        }, STATUS_TICK_MS);

        document.addEventListener('visibilitychange', function () {
            if (!document.hidden && Date.now() - lastRefreshAt >= REFRESH_INTERVAL_MS) {
                refreshAll();
            }
        });

        setLoading(true);
        fetchFolders()
            .then(function (folders) {
                allFolders = folders;
                filterMode = initialFilter();
                setLoading(false);
                render(false);
                if (selectedFolderId) {
                    updateMainPanelBadges(selectedFolderId);
                }
                scrollSelectedIntoView();
                lastRefreshAt = Date.now();
                updateRefreshStatus();
            })
            .catch(function (error) {
                setLoading(false);
                if (controlsEl) {
                    controlsEl.classList.add('d-none');
                }
                setError(error.message || 'Could not load folders.');
            });
    }

    document.addEventListener('DOMContentLoaded', initDashboardFolders);
})();
