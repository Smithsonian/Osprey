(function () {
    'use strict';

    var filesTableFilter = 'all';
    var activeProjectChecks = [];

    var BADGE_CLASS = {
        OK: 'file-result-badge file-result-badge--ok',
        Failed: 'file-result-badge file-result-badge--failed',
        Pending: 'file-result-badge file-result-badge--pending'
    };

    var FILE_CHECK_LABELS = {
        file_name: 'File name',
        tif_compression: 'TIF compression',
        tifpages: 'TIF pages',
        magick: 'ImageMagick',
        jhove: 'JHOVE',
        unique_file: 'Unique file',
        raw_pair: 'RAW pair',
        valid_name: 'Valid name',
        old_name: 'Old name',
        derivative: 'Derivative',
        prefix: 'Prefix',
        sequence: 'Sequence',
        tesseract: 'Tesseract',
        filename: 'Filename',
        md5: 'MD5',
        md5_raw: 'MD5 RAW',
        unique_other: 'Unique other'
    };

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function labelCheck(name) {
        if (FILE_CHECK_LABELS[name]) {
            return FILE_CHECK_LABELS[name];
        }
        return name.replace(/_/g, ' ').replace(/\b\w/g, function (char) {
            return char.toUpperCase();
        });
    }

    function normalizeStatus(value) {
        if (value === null || value === undefined || value === '') {
            return 'Pending';
        }
        return String(value);
    }

    function renderBadge(status) {
        var cls = BADGE_CLASS[status];
        if (!cls) {
            return escapeHtml(status);
        }
        return '<span class="' + cls + '">' + escapeHtml(status) + '</span>';
    }

    function rowHasStatus(row, status) {
        for (var i = 0; i < activeProjectChecks.length; i++) {
            if (normalizeStatus(row[activeProjectChecks[i]]) === status) {
                return true;
            }
        }
        return false;
    }

    function defaultOrder(files, projectChecks) {
        for (var c = 0; c < projectChecks.length; c++) {
            var check = projectChecks[c];
            for (var f = 0; f < files.length; f++) {
                if (normalizeStatus(files[f][check]) === 'Failed') {
                    return [[c + 1, 'asc']];
                }
            }
        }
        return [[0, 'asc']];
    }

    function fileDetailPath(fileId, transcription) {
        if (String(transcription) === '1') {
            return '/file_transcription/' + fileId + '/';
        }
        return '/file/' + fileId + '/';
    }

    function buildColumns(projectChecks, transcription) {
        var columns = [{
            title: 'File name',
            data: 'file_name',
            render: function (data, type, row) {
                if (type === 'display') {
                    var href = fileDetailPath(row.file_id, transcription);
                    return '<a href="' + href + '" title="Details of ' + escapeHtml(data) + '">' +
                        escapeHtml(data) + '</a>';
                }
                return data;
            }
        }];

        projectChecks.forEach(function (check) {
            columns.push({
                title: labelCheck(check),
                data: check,
                defaultContent: 'Pending',
                render: function (data, type) {
                    var status = normalizeStatus(data);
                    if (type === 'display') {
                        return renderBadge(status);
                    }
                    return status;
                }
            });
        });

        return columns;
    }

    $.fn.dataTable.ext.search.push(function (settings, data, dataIndex) {
        if (settings.nTable.id !== 'files_table') {
            return true;
        }
        if (filesTableFilter === 'all') {
            return true;
        }
        var row = $(settings.nTable).DataTable().row(dataIndex).data();
        if (!row) {
            return true;
        }
        if (filesTableFilter === 'failed') {
            return rowHasStatus(row, 'Failed');
        }
        if (filesTableFilter === 'pending') {
            return rowHasStatus(row, 'Pending');
        }
        return true;
    });

    function setLoading(isLoading) {
        $('#files-table-loading').toggleClass('d-none', !isLoading);
    }

    function setError(message) {
        var errorEl = document.getElementById('files-table-error');
        if (!errorEl) {
            return;
        }
        if (message) {
            errorEl.textContent = message;
            errorEl.classList.remove('d-none');
        } else {
            errorEl.textContent = '';
            errorEl.classList.add('d-none');
        }
    }

    function initFilesTableFromJson(panel) {
        var filesUrl = panel.getAttribute('data-files-url');
        var transcription = panel.getAttribute('data-transcription') || '0';
        var $table = $('#files_table');

        if (!filesUrl || !$table.length || $.fn.dataTable.isDataTable($table)) {
            return;
        }

        setLoading(true);
        setError('');

        fetch(filesUrl, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Could not load files (' + response.status + ')');
                }
                return response.json();
            })
            .then(function (payload) {
                var files = payload.files || [];
                var projectChecks = payload.project_checks || [];
                activeProjectChecks = projectChecks.slice();

                setLoading(false);
                $('#files-table-wrap').removeClass('d-none');

                var table = $table.DataTable({
                    data: files,
                    columns: buildColumns(projectChecks, transcription),
                    dom: 'Bfrtip',
                    buttons: ['csvHtml5', 'excelHtml5'],
                    order: defaultOrder(files, projectChecks),
                    columnDefs: [{
                        targets: 0,
                        createdCell: function (td) {
                            $(td).attr('scope', 'row');
                        }
                    }],
                    lengthMenu: [[25, 50, 100, -1], [25, 50, 100, 'All']],
                    rowCallback: function (row, data) {
                        $(row).toggleClass('dashboard-files-row-failed', rowHasStatus(data, 'Failed'));
                    }
                });

                $('.dashboard-files-filters [data-files-filter]').on('click', function () {
                    filesTableFilter = $(this).data('files-filter');
                    $('.dashboard-files-filters [data-files-filter]').removeClass('active');
                    $(this).addClass('active');
                    table.draw();
                });
            })
            .catch(function (error) {
                setLoading(false);
                setError(error.message || 'Could not load files.');
            });
    }

    function initDashboardFiles() {
        var panel = document.getElementById('dashboard-files-panel');
        if (!panel) {
            return;
        }
        initFilesTableFromJson(panel);
    }

    document.addEventListener('DOMContentLoaded', initDashboardFiles);
}());
