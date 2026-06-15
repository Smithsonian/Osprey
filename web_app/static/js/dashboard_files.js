(function () {
    'use strict';

    var filesTableFilter = 'all';

    var BADGE_CLASS = {
        OK: 'file-result-badge file-result-badge--ok',
        Failed: 'file-result-badge file-result-badge--failed',
        Pending: 'file-result-badge file-result-badge--pending'
    };

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

    function initFilesTable(options) {
        var $table = $('#files_table');
        if (!$table.length || $.fn.dataTable.isDataTable($table)) {
            return;
        }

        var table = $table.DataTable({
            dom: 'Bfrtip',
            buttons: ['csvHtml5', 'excelHtml5'],
            order: options.order || [[0, 'asc']],
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

        $('.dashboard-files-filters [data-files-filter]').on('click', function () {
            filesTableFilter = $(this).data('files-filter');
            $('.dashboard-files-filters [data-files-filter]').removeClass('active');
            $(this).addClass('active');
            table.draw();
        });
    }

    window.OspreyDashboardFiles = {
        init: initFilesTable
    };
}());
