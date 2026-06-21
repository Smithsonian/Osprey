(function () {
    'use strict';

    var postprodFilter = 'all';
    var dataTableInstance = null;
    var filterHandlerRegistered = false;

    var BADGE_CLASS = {
        Completed: 'file-result-badge file-result-badge--ok',
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

    function labelFor(step) {
        return step.replace(/_/g, ' ').replace(/\b\w/g, function (ch) {
            return ch.toUpperCase();
        });
    }

    function findStep(filePostprocessing, stepName) {
        for (var i = 0; i < filePostprocessing.length; i++) {
            if (filePostprocessing[i].post_step === stepName) {
                return filePostprocessing[i];
            }
        }
        return { post_results: 'Pending', post_info: null };
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
            if (settings.nTable.id !== 'post_processing_table') {
                return true;
            }
            if (postprodFilter === 'all') {
                return true;
            }
            if (postprodFilter === 'failed') {
                return rowHasStatus(data, 'Failed');
            }
            if (postprodFilter === 'pending') {
                return rowHasStatus(data, 'Pending');
            }
            return true;
        });
    }

    function decorateStepCells(row, data) {
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
        var $table = $('#post_processing_table');
        if ($table.length && $.fn.dataTable.isDataTable($table)) {
            $table.DataTable().destroy();
        }
        $table.empty();
        dataTableInstance = null;
    }

    function computeSortColumn(projectPostprocessing, files) {
        for (var i = 0; i < projectPostprocessing.length; i++) {
            var step = projectPostprocessing[i];
            for (var j = 0; j < files.length; j++) {
                if (findStep(files[j].file_postprocessing, step).post_results === 'Failed') {
                    return i + 1;
                }
            }
        }
        return 0;
    }

    function buildTableDom(files, projectPostprocessing, transcription, appRoot) {
        var columns = ['File name'].concat(projectPostprocessing.map(labelFor));

        var thead = '<thead><tr>' + columns.map(function (col) {
            return '<th scope="col">' + escapeHtml(col) + '</th>';
        }).join('') + '</tr></thead>';

        var bodyRows = files.map(function (file) {
            var cells = [fileLinkHtml(file.file_name, file.file_id, transcription, appRoot)];
            projectPostprocessing.forEach(function (step) {
                cells.push(findStep(file.file_postprocessing, step).post_results);
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

    function initDataTable(files, projectPostprocessing, transcription, appRoot) {
        destroyTable();
        registerFilter();

        var $table = $('#post_processing_table');
        $table.html(buildTableDom(files, projectPostprocessing, transcription, appRoot));

        var sortCol = computeSortColumn(projectPostprocessing, files);
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
                decorateStepCells(row, data);
            }
        });

        $('.dashboard-files-filters [data-postprod-filter]').off('click.dashboardPostprod').on('click.dashboardPostprod', function () {
            postprodFilter = $(this).data('postprod-filter');
            $('.dashboard-files-filters [data-postprod-filter]').removeClass('active');
            $(this).addClass('active');
            dataTableInstance.draw();
        });
    }

    function panelConfig(panel) {
        return {
            transcription: parseInt(panel.getAttribute('data-transcription') || '0', 10) === 1,
            appRoot: panel.getAttribute('data-app-root') || ''
        };
    }

    function setLoading() {
        $('#dashboard-postprod-loading').removeClass('d-none');
        $('#dashboard-postprod-table-wrap').addClass('d-none');
        $('#dashboard-postprod-empty').addClass('d-none');
        $('#dashboard-postprod-error').addClass('d-none');
    }

    function showError(message) {
        $('#dashboard-postprod-loading').addClass('d-none');
        $('#dashboard-postprod-table-wrap').addClass('d-none');
        $('#dashboard-postprod-empty').addClass('d-none');
        $('#dashboard-postprod-error').removeClass('d-none').text(message);
    }

    function showEmpty(folderName) {
        $('#dashboard-postprod-loading').addClass('d-none');
        $('#dashboard-postprod-table-wrap').addClass('d-none');
        $('#dashboard-postprod-empty').removeClass('d-none');
        $('#dashboard-postprod-count').text('0 files');
        if (folderName) {
            $('#dashboard-postprod-folder-name').text(folderName);
        }
    }

    function showTable(data, panel) {
        var config = panelConfig(panel);
        var projectPostprocessing = data.project_postprocessing || [];
        var files = data.files || [];

        $('#dashboard-postprod-loading').addClass('d-none');
        $('#dashboard-postprod-error').addClass('d-none');
        $('#dashboard-postprod-folder-name').text(data.folder || '');
        $('#dashboard-postprod-count').text(files.length + ' file' + (files.length !== 1 ? 's' : ''));

        if (!files.length) {
            showEmpty(data.folder || '');
            return;
        }

        $('#dashboard-postprod-empty').addClass('d-none');
        $('#dashboard-postprod-table-wrap').removeClass('d-none');
        initDataTable(files, projectPostprocessing, config.transcription, config.appRoot);
    }

    function loadFromUrl(filesUrl, panel) {
        setLoading();
        return fetch(filesUrl, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Could not load post-processing steps (' + response.status + ')');
                }
                return response.json();
            })
            .then(function (data) {
                showTable(data, panel);
                return data;
            })
            .catch(function (error) {
                showError(error.message || 'Could not load post-processing steps.');
            });
    }

    function loadFromPanel() {
        var panel = document.getElementById('dashboard-postprod-panel');
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
        var panel = document.getElementById('dashboard-postprod-panel');
        if (!panel) {
            return;
        }
        var urlBase = panel.getAttribute('data-api-path') || '/api/folders/';
        var url = urlBase + encodeURIComponent(folderId) + '/files';
        panel.setAttribute('data-files-url', url);
        panel.setAttribute('data-folder-id', String(folderId));
        postprodFilter = 'all';
        $('.dashboard-files-filters [data-postprod-filter]').removeClass('active');
        $('.dashboard-files-filters [data-postprod-filter="all"]').addClass('active');
        return loadFromUrl(url, panel);
    }

    window.OspreyDashboardPostprocessing = {
        loadFromPanel: loadFromPanel,
        loadForFolder: loadForFolder
    };
}());
