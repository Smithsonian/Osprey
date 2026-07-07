(function () {
    'use strict';

    var TRANSCRIPTION_QC_BADGE = {
        0: '<span class="badge bg-success">Transcription OK</span>',
        1: '<span class="badge bg-danger">Critical Issue</span>',
        2: '<span class="badge bg-warning">Major Issue</span>',
        3: '<span class="badge bg-warning">Minor Issue</span>',
        9: '<span class="badge bg-secondary">Pending</span>'
    };

    var dataTableInstances = [];

    function escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function sourceDomId(sourceId) {
        return String(sourceId || 'source').replace(/[^A-Za-z0-9_-]/g, '_');
    }

    function fileLinkHtml(file, appRoot) {
        var path = appRoot + '/file_transcription/' + file.file_id + '/';
        return '<a href="' + path + '" title="File Details" target="_blank">' +
            escapeHtml(file.file_name) + '</a>';
    }

    function statusBadge(statusValue) {
        if (parseInt(statusValue, 10) === 0) {
            return '<span class="badge bg-success ms-2">QC Passed</span>';
        }
        if (parseInt(statusValue, 10) === 1) {
            return '<span class="badge bg-danger ms-2">QC Failed</span>';
        }
        return '<span class="badge bg-secondary ms-2">QC Pending</span>';
    }

    function destroyTables() {
        dataTableInstances.forEach(function (instance) {
            instance.destroy();
        });
        dataTableInstances = [];
    }

    function buildTableDom(source, appRoot) {
        var thead = '<thead><tr><th scope="col">file_name</th><th scope="col">qc_notes</th><th scope="col">qc_results</th></tr></thead>';
        var bodyRows = (source.files || []).map(function (file) {
            return '<tr>' +
                '<td scope="row">' + fileLinkHtml(file, appRoot) + '</td>' +
                '<td>' + escapeHtml(file.qc_notes || '') + '</td>' +
                '<td>' + (TRANSCRIPTION_QC_BADGE[file.qc_results] || '') + '</td>' +
                '</tr>';
        }).join('');
        return thead + '<tbody>' + bodyRows + '</tbody>';
    }

    function buildSourceItem(source, index, appRoot) {
        var domId = sourceDomId(source.source_id);
        var headingId = 'transcription_qc_heading_' + domId;
        var panelId = 'transcription_qc_panel_' + domId;
        var tableId = 'transcription_qc_details_table_' + domId;
        var notesHtml = source.qc_folder_info ?
            '<p class="mb-2">Notes: ' + escapeHtml(source.qc_folder_info) + '</p>' : '';
        var metaParts = [];
        if (source.qc_by) {
            metaParts.push('QC by ' + escapeHtml(source.qc_by));
        }
        if (source.updated_at) {
            metaParts.push('Updated ' + escapeHtml(source.updated_at));
        }
        var metaHtml = metaParts.length ?
            '<p class="small text-muted mb-2">' + metaParts.join(' | ') + '</p>' : '';

        return '<div class="accordion-item">' +
            '<h2 class="accordion-header" id="' + headingId + '">' +
                '<button class="accordion-button collapsed" type="button" ' +
                        'data-bs-toggle="collapse" data-bs-target="#' + panelId + '" ' +
                        'aria-expanded="false" aria-controls="' + panelId + '">' +
                    'Transcription QC Details - ' + escapeHtml(source.source_name || 'Source ' + (index + 1)) +
                    statusBadge(source.qc_status_value) +
                '</button>' +
            '</h2>' +
            '<div id="' + panelId + '" class="accordion-collapse collapse" ' +
                 'aria-labelledby="' + headingId + '" data-bs-parent="#transcription_qc_accordion">' +
                '<div class="accordion-body">' +
                    metaHtml +
                    notesHtml +
                    '<table id="' + tableId + '" class="display compact table-striped w-100">' +
                        buildTableDom(source, appRoot) +
                    '</table>' +
                '</div>' +
            '</div>' +
        '</div>';
    }

    function initializeTables(sources) {
        (sources || []).forEach(function (source) {
            var tableId = '#transcription_qc_details_table_' + sourceDomId(source.source_id);
            var $table = $(tableId);
            if ($table.length) {
                dataTableInstances.push($table.DataTable({
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
                }));
            }
        });
    }

    function bindAccordionAdjust() {
        var accordion = document.getElementById('transcription_qc_accordion');
        if (!accordion || accordion.getAttribute('data-adjust-bound') === '1') {
            return;
        }
        accordion.setAttribute('data-adjust-bound', '1');
        accordion.addEventListener('shown.bs.collapse', function () {
            dataTableInstances.forEach(function (instance) {
                instance.columns.adjust().draw(false);
            });
        });
    }

    function showLoading() {
        document.getElementById('dashboard-transcription-qc-loading').classList.remove('d-none');
        document.getElementById('dashboard-transcription-qc-content').classList.add('d-none');
        document.getElementById('dashboard-transcription-qc-error').classList.add('d-none');
    }

    function showError(message) {
        document.getElementById('dashboard-transcription-qc-loading').classList.add('d-none');
        document.getElementById('dashboard-transcription-qc-content').classList.add('d-none');
        var errorEl = document.getElementById('dashboard-transcription-qc-error');
        errorEl.textContent = message;
        errorEl.classList.remove('d-none');
    }

    function showContent(data, panel) {
        document.getElementById('dashboard-transcription-qc-loading').classList.add('d-none');
        document.getElementById('dashboard-transcription-qc-error').classList.add('d-none');

        destroyTables();
        var contentEl = document.getElementById('dashboard-transcription-qc-content');
        var accordion = document.getElementById('transcription_qc_accordion');
        accordion.innerHTML = '';

        if (!data.qc_checked || !(data.sources || []).length) {
            contentEl.classList.add('d-none');
            return;
        }

        var appRoot = panel.getAttribute('data-app-root') || '';
        accordion.innerHTML = data.sources.map(function (source, index) {
            return buildSourceItem(source, index, appRoot);
        }).join('');

        initializeTables(data.sources);
        bindAccordionAdjust();
        contentEl.classList.remove('d-none');
    }

    function loadFromUrl(url, panel) {
        showLoading();
        return fetch(url, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Could not load transcription QC information (' + response.status + ')');
                }
                return response.json();
            })
            .then(function (data) {
                showContent(data, panel);
                return data;
            })
            .catch(function (error) {
                showError(error.message || 'Could not load transcription QC information.');
            });
    }

    function loadFromPanel() {
        var panel = document.getElementById('dashboard-transcription-qc-panel');
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
        var panel = document.getElementById('dashboard-transcription-qc-panel');
        if (!panel) {
            return;
        }
        var urlBase = panel.getAttribute('data-api-path') || '/api/folders/';
        var url = urlBase + encodeURIComponent(folderId) + '/transcription_qc';
        panel.setAttribute('data-qc-url', url);
        panel.setAttribute('data-folder-id', String(folderId));
        return loadFromUrl(url, panel);
    }

    window.OspreyDashboardTranscriptionQc = {
        loadFromPanel: loadFromPanel,
        loadForFolder: loadForFolder
    };
}());
