(function () {
    'use strict';

    var filesTableFilter = 'all';
    var dataTableInstance = null;
    var filterHandlerRegistered = false;

    var BADGE_CLASS = {
        OK: 'file-result-badge file-result-badge--ok',
        Failed: 'file-result-badge file-result-badge--failed',
        Pending: 'file-result-badge file-result-badge--pending'
    };

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

    function labelFor(check, checkLabels) {
        if (checkLabels && checkLabels[check]) {
            return checkLabels[check];
        }
        return check.replace(/_/g, ' ').replace(/\b\w/g, function (ch) {
            return ch.toUpperCase();
        });
    }

    function findCheck(fileChecks, checkName) {
        for (var i = 0; i < fileChecks.length; i++) {
            if (fileChecks[i].file_check === checkName) {
                return fileChecks[i];
            }
        }
        return { check_results: 'Pending', check_info: null };
    }

    function fileLinkHtml(fileName, fileId, transcription, appRoot) {
        var path = transcription ?
            appRoot + '/file_transcription/' + fileId + '/' :
            appRoot + '/file/' + fileId + '/';
        return '<a href="' + path + '" title="Details of File ' + escapeHtml(fileName) + '">' +
            escapeHtml(fileName) + '</a>';
    }

    function registerFilter() {
        if (filterHandlerRegistered) {
            return;
        }
        filterHandlerRegistered = true;
        $.fn.dataTable.ext.search.push(function (settings, data) {
            if (settings.nTable.id !== 'files_table') {
                return true;
            }
            if (filesTableFilter === 'all') {
                return true;
            }
            if (filesTableFilter === 'failed') {
                return rowHasStatus(data, 'Failed');
            }
            if (filesTableFilter === 'pending') {
                return rowHasStatus(data, 'Pending');
            }
            return true;
        });
    }

    function decorateCheckCells(row, data) {
        var hasFailed = false;

        for (var i = 1; i < data.length; i++) {
            var status = statusFromCell(data[i]);
            var $cell = $(row).find('td:eq(' + i + ')');

            if (BADGE_CLASS[status]) {
                $cell.html('<span class="' + BADGE_CLASS[status] + '">' + status + '</span>');
            }
            if (status === 'Failed') {
                hasFailed = true;
            }
        }

        $(row).toggleClass('dashboard-files-row-failed', hasFailed);
    }

    function destroyTable() {
        var $table = $('#files_table');
        if ($table.length && $.fn.dataTable.isDataTable($table)) {
            $table.DataTable().destroy();
        }
        $table.empty();
        dataTableInstance = null;
    }

    function computeSortColumn(projectChecks, files) {
        for (var i = 0; i < projectChecks.length; i++) {
            var check = projectChecks[i];
            for (var j = 0; j < files.length; j++) {
                if (findCheck(files[j].file_checks, check).check_results === 'Failed') {
                    return i + 1;
                }
            }
        }
        return 0;
    }

    function buildTableDom(files, projectChecks, transcription, appRoot, checkLabels) {
        var columns = ['File name'].concat(projectChecks.map(function (check) {
            return labelFor(check, checkLabels);
        }));

        var thead = '<thead><tr>' + columns.map(function (col) {
            return '<th scope="col">' + escapeHtml(col) + '</th>';
        }).join('') + '</tr></thead>';

        var bodyRows = files.map(function (file) {
            var cells = [fileLinkHtml(file.file_name, file.file_id, transcription, appRoot)];
            projectChecks.forEach(function (check) {
                cells.push(findCheck(file.file_checks, check).check_results);
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

    function initDataTable(files, projectChecks, transcription, appRoot, checkLabels) {
        destroyTable();
        registerFilter();

        var $table = $('#files_table');
        $table.html(buildTableDom(files, projectChecks, transcription, appRoot, checkLabels));

        var sortCol = computeSortColumn(projectChecks, files);
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
                decorateCheckCells(row, data);
            }
        });

        $('.dashboard-files-filters [data-files-filter]').off('click.dashboardFiles').on('click.dashboardFiles', function () {
            filesTableFilter = $(this).data('files-filter');
            $('.dashboard-files-filters [data-files-filter]').removeClass('active');
            $(this).addClass('active');
            dataTableInstance.draw();
        });
    }

    function panelConfig(panel) {
        return {
            checkLabels: JSON.parse(panel.getAttribute('data-check-labels') || '{}'),
            transcription: parseInt(panel.getAttribute('data-transcription') || '0', 10) === 1,
            appRoot: panel.getAttribute('data-app-root') || ''
        };
    }

    function setLoading() {
        $('#dashboard-files-loading').removeClass('d-none');
        $('#dashboard-files-table-wrap').addClass('d-none');
        $('#dashboard-files-empty').addClass('d-none');
        $('#dashboard-files-error').addClass('d-none');
    }

    function showError(message) {
        $('#dashboard-files-loading').addClass('d-none');
        $('#dashboard-files-table-wrap').addClass('d-none');
        $('#dashboard-files-empty').addClass('d-none');
        $('#dashboard-files-error').removeClass('d-none').text(message);
    }

    function showEmpty(folderName) {
        $('#dashboard-files-loading').addClass('d-none');
        $('#dashboard-files-table-wrap').addClass('d-none');
        $('#dashboard-files-empty').removeClass('d-none');
        $('#dashboard-files-count').text('0 files');
        if (folderName) {
            $('#dashboard-files-folder-name').text(folderName);
        }
    }

    function showTable(data, panel) {
        var config = panelConfig(panel);
        var projectChecks = data.project_checks || [];
        var files = data.files || [];

        $('#dashboard-files-loading').addClass('d-none');
        $('#dashboard-files-error').addClass('d-none');
        $('#dashboard-files-folder-name').text(data.folder || '');
        $('#dashboard-files-count').text(files.length + ' file' + (files.length !== 1 ? 's' : ''));

        if (!files.length) {
            showEmpty(data.folder || '');
            return;
        }

        $('#dashboard-files-empty').addClass('d-none');
        $('#dashboard-files-table-wrap').removeClass('d-none');
        initDataTable(files, projectChecks, config.transcription, config.appRoot, config.checkLabels);
    }

    function loadFromUrl(filesUrl, panel) {
        setLoading();
        return fetch(filesUrl, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Could not load files (' + response.status + ')');
                }
                return response.json();
            })
            .then(function (data) {
                showTable(data, panel);
                return data;
            })
            .catch(function (error) {
                showError(error.message || 'Could not load files.');
            });
    }

    function loadFromPanel() {
        var panel = document.getElementById('dashboard-files-panel');
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
        var panel = document.getElementById('dashboard-files-panel');
        if (!panel) {
            return;
        }
        var urlBase = panel.getAttribute('data-api-path') || '/api/folders/';
        var url = urlBase + encodeURIComponent(folderId) + '/files';
        panel.setAttribute('data-files-url', url);
        panel.setAttribute('data-folder-id', String(folderId));
        filesTableFilter = 'all';
        $('.dashboard-files-filters [data-files-filter]').removeClass('active');
        $('.dashboard-files-filters [data-files-filter="all"]').addClass('active');
        return loadFromUrl(url, panel);
    }

    window.OspreyDashboardFiles = {
        loadFromPanel: loadFromPanel,
        loadForFolder: loadForFolder
    };
}());
