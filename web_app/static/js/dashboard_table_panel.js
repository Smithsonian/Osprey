/**
 * Shared loader/table/filter logic for dashboard folder-detail panels
 * that render a per-file status table (Checks, Post-processing).
 * Config-driven so dashboard_files.js and dashboard_postprocessing.js
 * can each just supply ids/field names instead of duplicating this code.
 */
(function () {
    'use strict';

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function stripHtml(html) {
        var tmp = document.createElement('div');
        tmp.innerHTML = html;
        return (tmp.textContent || tmp.innerText || '').trim();
    }

    function statusFromCell(cellData) {
        return stripHtml(String(cellData || ''));
    }

    function rowHasStatus(data, status) {
        for (var i = 1; i < data.length; i++) {
            if (statusFromCell(data[i]) === status) {
                return true;
            }
        }
        return false;
    }

    function fileLinkHtml(fileName, fileId, transcription, appRoot) {
        var path = transcription ?
            appRoot + '/file_transcription/' + fileId + '/' :
            appRoot + '/file/' + fileId + '/';
        return '<a href="' + path + '" title="Details of File ' + escapeHtml(fileName) + '">' +
            escapeHtml(fileName) + '</a>';
    }

    function create(cfg) {
        var tableFilter = 'all';
        var dataTableInstance = null;
        var filterHandlerRegistered = false;
        var filterSelector = '.dashboard-files-filters [data-' + cfg.filterKey + ']';
        // JSON of the last payload drawn; a background refresh with the same
        // data leaves the table (page, sort, search) untouched.
        var lastPayloadKey = null;

        function labelFor(name, labels) {
            if (labels && labels[name]) {
                return labels[name];
            }
            return name.replace(/_/g, ' ').replace(/\b\w/g, function (ch) {
                return ch.toUpperCase();
            });
        }

        function findItem(items, name) {
            for (var i = 0; i < items.length; i++) {
                if (items[i][cfg.nameKey] === name) {
                    return items[i];
                }
            }
            var fallback = {};
            fallback[cfg.resultKey] = 'Pending';
            return fallback;
        }

        function registerFilter() {
            if (filterHandlerRegistered) {
                return;
            }
            filterHandlerRegistered = true;
            $.fn.dataTable.ext.search.push(function (settings, data) {
                if (settings.nTable.id !== cfg.tableId) {
                    return true;
                }
                if (tableFilter === 'all') {
                    return true;
                }
                if (tableFilter === 'failed') {
                    return rowHasStatus(data, 'Failed');
                }
                if (tableFilter === 'pending') {
                    return rowHasStatus(data, 'Pending');
                }
                return true;
            });
        }

        function decorateCells(row, data) {
            var hasFailed = false;

            for (var i = 1; i < data.length; i++) {
                var status = statusFromCell(data[i]);
                var $cell = $(row).find('td:eq(' + i + ')');

                if (cfg.badgeClass[status]) {
                    $cell.html('<span class="' + cfg.badgeClass[status] + '">' + status + '</span>');
                }
                if (status === 'Failed') {
                    hasFailed = true;
                }
            }

            $(row).toggleClass('dashboard-files-row-failed', hasFailed);
        }

        function setActiveFilterButton() {
            $(filterSelector).each(function () {
                var isActive = $(this).data(cfg.filterKey) === tableFilter;
                $(this).toggleClass('active', isActive).attr('aria-pressed', isActive ? 'true' : 'false');
            });
        }

        function fileHasStatus(file, status) {
            var items = file[cfg.itemsKey] || [];
            for (var i = 0; i < items.length; i++) {
                if (items[i][cfg.resultKey] === status) {
                    return true;
                }
            }
            return false;
        }

        // Fill the "(n)" badges on the All / Failed / Pending buttons.
        function updateFilterCounts(files) {
            var counts = {
                all: files.length,
                failed: files.filter(function (f) { return fileHasStatus(f, 'Failed'); }).length,
                pending: files.filter(function (f) { return fileHasStatus(f, 'Pending'); }).length
            };
            $(filterSelector).each(function () {
                var mode = $(this).data(cfg.filterKey);
                $(this).find('[data-count-for]').text(counts[mode] === undefined ? '' : counts[mode]);
            });
        }

        function captureTableState() {
            if (!dataTableInstance) {
                return null;
            }
            return {
                page: dataTableInstance.page(),
                length: dataTableInstance.page.len(),
                order: dataTableInstance.order(),
                search: dataTableInstance.search()
            };
        }

        function restoreTableState(state) {
            if (!state || !dataTableInstance) {
                return;
            }
            dataTableInstance.page.len(state.length).order(state.order).search(state.search).draw();
            var pages = dataTableInstance.page.info().pages;
            if (pages > 0) {
                dataTableInstance.page(Math.min(state.page, pages - 1)).draw('page');
            }
        }

        function destroyTable() {
            var $table = $('#' + cfg.tableId);
            if ($table.length && $.fn.dataTable.isDataTable($table)) {
                $table.DataTable().destroy();
            }
            $table.empty();
            dataTableInstance = null;
        }

        function computeSortColumn(columnNames, files) {
            for (var i = 0; i < columnNames.length; i++) {
                var name = columnNames[i];
                for (var j = 0; j < files.length; j++) {
                    var items = files[j][cfg.itemsKey] || [];
                    if (findItem(items, name)[cfg.resultKey] === 'Failed') {
                        return i + 1;
                    }
                }
            }
            return 0;
        }

        function buildTableDom(files, columnNames, transcription, appRoot, labels) {
            var columns = ['File name'].concat(columnNames.map(function (name) {
                return labelFor(name, labels);
            }));

            var thead = '<thead><tr>' + columns.map(function (col) {
                return '<th scope="col">' + escapeHtml(col) + '</th>';
            }).join('') + '</tr></thead>';

            var bodyRows = files.map(function (file) {
                var cells = [fileLinkHtml(file.file_name, file.file_id, transcription, appRoot)];
                columnNames.forEach(function (name) {
                    var items = file[cfg.itemsKey] || [];
                    cells.push(findItem(items, name)[cfg.resultKey]);
                });
                return '<tr>' + cells.map(function (cell, idx) {
                    if (idx === 0) {
                        return '<td scope="row">' + cell + '</td>';
                    }
                    return '<td>' + escapeHtml(cell) + '</td>';
                }).join('') + '</tr>';
            }).join('');

            return thead + '<tbody>' + bodyRows + '</tbody>';
        }

        function initDataTable(files, columnNames, transcription, appRoot, labels, previousState) {
            // Hold the wrapper's height while the table is rebuilt so a
            // refresh doesn't make the page jump.
            var wrap = document.getElementById(cfg.idPrefix + '-table-wrap');
            if (wrap && previousState) {
                wrap.style.minHeight = wrap.offsetHeight + 'px';
            }
            destroyTable();
            registerFilter();

            var $table = $('#' + cfg.tableId);
            $table.html(buildTableDom(files, columnNames, transcription, appRoot, labels));

            var sortCol = computeSortColumn(columnNames, files);
            dataTableInstance = $table.DataTable({
                dom: 'Bfrtip',
                buttons: ['csvHtml5', 'excelHtml5'],
                order: [[sortCol, 'asc']],
                columnDefs: [{
                    targets: 0,
                    createdCell: function (td) {
                        $(td).attr('scope', 'row');
                    }
                }],
                lengthMenu: [[25, 50, 100, -1], [25, 50, 100, 'All']],
                rowCallback: function (row, data) {
                    decorateCells(row, data);
                }
            });

            restoreTableState(previousState);
            if (wrap) {
                wrap.style.minHeight = '';
            }

            $(filterSelector).off('click.' + cfg.filterNamespace).on('click.' + cfg.filterNamespace, function () {
                tableFilter = $(this).data(cfg.filterKey);
                setActiveFilterButton();
                dataTableInstance.draw();
            });
            setActiveFilterButton();
        }

        function panelConfig(panel) {
            return {
                labels: JSON.parse(panel.getAttribute('data-check-labels') || '{}'),
                transcription: parseInt(panel.getAttribute('data-transcription') || '0', 10) === 1,
                appRoot: panel.getAttribute('data-app-root') || ''
            };
        }

        function setLoading() {
            $('#' + cfg.idPrefix + '-loading').removeClass('d-none');
            $('#' + cfg.idPrefix + '-table-wrap').addClass('d-none');
            $('#' + cfg.idPrefix + '-empty').addClass('d-none');
            $('#' + cfg.idPrefix + '-error').addClass('d-none');
        }

        function showError(message) {
            $('#' + cfg.idPrefix + '-loading').addClass('d-none');
            $('#' + cfg.idPrefix + '-table-wrap').addClass('d-none');
            $('#' + cfg.idPrefix + '-empty').addClass('d-none');
            $('#' + cfg.idPrefix + '-error').removeClass('d-none').text(message);
        }

        function showEmpty(folderName) {
            $('#' + cfg.idPrefix + '-loading').addClass('d-none');
            $('#' + cfg.idPrefix + '-table-wrap').addClass('d-none');
            $('#' + cfg.idPrefix + '-empty').removeClass('d-none');
            $('#' + cfg.idPrefix + '-count').text('0 files');
            updateFilterCounts([]);
            if (folderName) {
                $('#' + cfg.idPrefix + '-folder-name').text(folderName);
            }
        }

        function showTable(data, panel, silent) {
            var payloadKey = JSON.stringify(data);
            if (silent && payloadKey === lastPayloadKey) {
                return;
            }
            lastPayloadKey = payloadKey;
            var previousState = silent ? captureTableState() : null;
            var conf = panelConfig(panel);
            var columnNames = data[cfg.columnsKey] || [];
            var files = data.files || [];

            $('#' + cfg.idPrefix + '-loading').addClass('d-none');
            $('#' + cfg.idPrefix + '-error').addClass('d-none');
            $('#' + cfg.idPrefix + '-folder-name').text(data.folder || '');
            $('#' + cfg.idPrefix + '-count').text(files.length + ' file' + (files.length !== 1 ? 's' : ''));
            updateFilterCounts(files);
            if (data.last_updated) {
                $('#dashboard-folder-last-updated').text(data.last_updated);
            }

            if (!files.length) {
                showEmpty(data.folder || '');
                return;
            }

            $('#' + cfg.idPrefix + '-empty').addClass('d-none');
            $('#' + cfg.idPrefix + '-table-wrap').removeClass('d-none');
            initDataTable(files, columnNames, conf.transcription, conf.appRoot, conf.labels, previousState);
        }

        // silent: background refresh - no spinner, keep the current table on
        // failure (the error is passed on so the caller can report it).
        function loadFromUrl(url, panel, silent) {
            // Snapshot which folder this request is for. A newer loadForFolder()
            // call updates this attribute immediately, so if it no longer matches
            // when the response lands, a later request has already taken over —
            // discard this one instead of overwriting the panel with stale data.
            var requestFolderId = panel.getAttribute('data-folder-id');
            if (!silent) {
                setLoading();
            }
            return fetch(url, { credentials: 'same-origin' })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('Could not load ' + cfg.errorNoun + ' (' + response.status + ')');
                    }
                    return response.json();
                })
                .then(function (data) {
                    if (panel.getAttribute('data-folder-id') !== requestFolderId) {
                        return data;
                    }
                    showTable(data, panel, silent);
                    return data;
                })
                .catch(function (error) {
                    if (panel.getAttribute('data-folder-id') !== requestFolderId) {
                        return;
                    }
                    if (silent) {
                        throw error;
                    }
                    showError(error.message || ('Could not load ' + cfg.errorNoun + '.'));
                });
        }

        function loadFromPanel() {
            var panel = document.getElementById(cfg.panelId);
            if (!panel) {
                return;
            }
            var url = panel.getAttribute('data-files-url');
            if (!url) {
                return;
            }
            return loadFromUrl(url, panel);
        }

        function loadForFolder(folderId) {
            var panel = document.getElementById(cfg.panelId);
            if (!panel) {
                return;
            }
            var urlBase = panel.getAttribute('data-api-path') || '/api/folders/';
            var url = urlBase + encodeURIComponent(folderId) + '/files';
            panel.setAttribute('data-files-url', url);
            panel.setAttribute('data-folder-id', String(folderId));
            tableFilter = 'all';
            lastPayloadKey = null;
            setActiveFilterButton();
            return loadFromUrl(url, panel);
        }

        function refresh() {
            var panel = document.getElementById(cfg.panelId);
            if (!panel || !panel.getAttribute('data-files-url')) {
                return;
            }
            return loadFromUrl(panel.getAttribute('data-files-url'), panel, true);
        }

        return {
            loadFromPanel: loadFromPanel,
            loadForFolder: loadForFolder,
            refresh: refresh
        };
    }

    window.OspreyDashboardTablePanel = {
        create: create
    };
}());
