(function () {
    'use strict';

    var FILE_QC_BADGE = {
        0: '<span class="badge bg-success">Image OK</span>',
        1: '<span class="badge bg-danger">Critical Issue</span>',
        2: '<span class="badge bg-warning">Major Issue</span>',
        3: '<span class="badge bg-warning">Minor Issue</span>'
    };

    var dataTableInstance = null;
    var collapseBound = false;

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
            appRoot: panel.getAttribute('data-app-root') || ''
        };
    }

    function fileLinkHtml(file, transcription, appRoot) {
        var path = transcription ?
            appRoot + '/file_transcription/' + file.file_id + '/' :
            appRoot + '/file/' + file.file_id + '/';
        return '<a href="' + path + '" title="File Details" target="_blank">' +
            escapeHtml(file.file_name) + '</a>';
    }

    function destroyTable() {
        var $table = $('#qc_details_table');
        if ($table.length && $.fn.dataTable.isDataTable($table)) {
            $table.DataTable().destroy();
        }
        $table.empty();
        dataTableInstance = null;
    }

    function buildTableDom(files, transcription, appRoot) {
        var thead = '<thead><tr><th scope="col">file_name</th><th scope="col">qc_info</th><th scope="col">file_qc</th></tr></thead>';
        var bodyRows = files.map(function (file) {
            return '<tr>' +
                '<td scope="row">' + fileLinkHtml(file, transcription, appRoot) + '</td>' +
                '<td>' + escapeHtml(file.qc_info || '') + '</td>' +
                '<td>' + (FILE_QC_BADGE[file.file_qc] || '') + '</td>' +
                '</tr>';
        }).join('');
        return thead + '<tbody>' + bodyRows + '</tbody>';
    }

    function bindAccordionAdjust() {
        if (collapseBound) {
            return;
        }
        var qcAccordionPanel = document.getElementById('qc_accordion_panel');
        if (!qcAccordionPanel) {
            return;
        }
        collapseBound = true;
        qcAccordionPanel.addEventListener('shown.bs.collapse', function () {
            if (dataTableInstance) {
                dataTableInstance.columns.adjust().draw(false);
            }
        });
    }

    function showLoading() {
        document.getElementById('dashboard-qc-loading').classList.remove('d-none');
        document.getElementById('dashboard-qc-content').classList.add('d-none');
        document.getElementById('dashboard-qc-error').classList.add('d-none');
    }

    function showError(message) {
        document.getElementById('dashboard-qc-loading').classList.add('d-none');
        document.getElementById('dashboard-qc-content').classList.add('d-none');
        var errorEl = document.getElementById('dashboard-qc-error');
        errorEl.textContent = message;
        errorEl.classList.remove('d-none');
    }

    function showContent(data, panel) {
        document.getElementById('dashboard-qc-loading').classList.add('d-none');
        document.getElementById('dashboard-qc-error').classList.add('d-none');

        if (!data.qc_checked) {
            destroyTable();
            document.getElementById('dashboard-qc-content').classList.add('d-none');
            return;
        }

        var conf = panelConfig(panel);
        destroyTable();
        var $table = $('#qc_details_table');
        $table.html(buildTableDom(data.files || [], conf.transcription, conf.appRoot));
        dataTableInstance = $table.DataTable({
            dom: 'Bfrtip',
            buttons: ['csvHtml5', 'excelHtml5'],
            order: [],
            columnDefs: [{
                targets: 0,
                createdCell: function (td) {
                    $(td).attr('scope', 'row');
                }
            }],
            lengthMenu: [[25, 50, 100, -1], [25, 50, 100, 'All']]
        });

        var notesEl = document.getElementById('dashboard-qc-notes');
        var notesText = document.getElementById('dashboard-qc-notes-text');
        if (data.qc_folder_info) {
            notesText.textContent = data.qc_folder_info;
            notesEl.classList.remove('d-none');
        } else {
            notesEl.classList.add('d-none');
        }

        bindAccordionAdjust();
        document.getElementById('dashboard-qc-content').classList.remove('d-none');
    }

    function loadFromUrl(url, panel) {
        showLoading();
        return fetch(url, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Could not load QC information (' + response.status + ')');
                }
                return response.json();
            })
            .then(function (data) {
                showContent(data, panel);
                return data;
            })
            .catch(function (error) {
                showError(error.message || 'Could not load QC information.');
            });
    }

    function loadFromPanel() {
        var panel = document.getElementById('dashboard-qc-panel');
        if (!panel) {
            return;
        }
        var url = panel.getAttribute('data-qc-url');
        if (!url) {
            return;
        }
        return loadFromUrl(url, panel);
    }

    function loadForFolder(folderId) {
        var panel = document.getElementById('dashboard-qc-panel');
        if (!panel) {
            return;
        }
        var urlBase = panel.getAttribute('data-api-path') || '/api/folders/';
        var url = urlBase + encodeURIComponent(folderId) + '/qc';
        panel.setAttribute('data-qc-url', url);
        panel.setAttribute('data-folder-id', String(folderId));
        return loadFromUrl(url, panel);
    }

    window.OspreyDashboardQc = {
        loadFromPanel: loadFromPanel,
        loadForFolder: loadForFolder
    };
}());
