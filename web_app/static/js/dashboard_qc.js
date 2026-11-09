(function () {
    'use strict';

    var FILE_QC_BADGE = {
        0: '<span class="badge text-bg-success">Image OK</span>',
        1: '<span class="badge text-bg-danger">Critical Issue</span>',
        2: '<span class="badge text-bg-warning">Major Issue</span>',
        3: '<span class="badge text-bg-warning">Minor Issue</span>',
        9: '<span class="badge text-bg-secondary">Not reviewed</span>'
    };

    var dataTableInstance = null;
    var collapseBound = false;
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
            appRoot: panel.getAttribute('data-app-root') || ''
        };
    }

    function fileLinkHtml(file, transcription, appRoot) {
        var path = transcription ?
            appRoot + '/file_transcription/' + file.file_id + '/' :
            appRoot + '/file/' + file.file_id + '/';
        return '<a href="' + path + '" title="File Details">' +
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
        var thead = '<thead><tr><th scope="col">File</th><th scope="col">QC notes</th><th scope="col">Result</th></tr></thead>';
        var bodyRows = files.map(function (file) {
            return '<tr>' +
                '<td scope="row">' + fileLinkHtml(file, transcription, appRoot) + '</td>' +
                '<td>' + escapeHtml(file.qc_info || '') + '</td>' +
                '<td>' + (FILE_QC_BADGE[file.file_qc] || FILE_QC_BADGE[9]) + '</td>' +
                '</tr>';
        }).join('');
        return thead + '<tbody>' + bodyRows + '</tbody>';
    }

    function folderStatusBadge(qcStatus) {
        var value = parseInt(qcStatus, 10);
        if (value === 0) {
            return '<span class="badge text-bg-success">Passed</span>';
        }
        if (value === 1) {
            return '<span class="badge text-bg-danger">Failed</span>';
        }
        return '<span class="badge text-bg-warning">Pending</span>';
    }

    function plural(n, word) {
        return n + ' ' + word + (n === 1 ? '' : 's');
    }

    // One-line result shown on the collapsed accordion button, so the outcome
    // is visible without expanding the file list.
    function summaryHtml(data) {
        var files = data.files || [];
        var counts = { 0: 0, 1: 0, 2: 0, 3: 0, 9: 0 };
        files.forEach(function (file) {
            var value = parseInt(file.file_qc, 10);
            counts[counts.hasOwnProperty(value) ? value : 9] += 1;
        });

        var parts = [plural(files.length, 'file') + ' sampled'];
        var issues = [];
        if (counts[1]) {
            issues.push(counts[1] + ' critical');
        }
        if (counts[2]) {
            issues.push(counts[2] + ' major');
        }
        if (counts[3]) {
            issues.push(counts[3] + ' minor');
        }
        if (issues.length) {
            parts.push(issues.join(', '));
        } else if (files.length && !counts[9]) {
            parts.push('no issues');
        }
        if (counts[9]) {
            parts.push(counts[9] + ' not reviewed');
        }

        return '<span class="dashboard-qc-summary">' +
            '<span class="fw-semibold">Visual Image QC</span>' +
            folderStatusBadge(data.qc_status) +
            '<span class="dashboard-qc-summary-detail">' + escapeHtml(parts.join(' · ')) + '</span>' +
            '</span>';
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

    function showContent(data, panel, silent) {
        var payloadKey = JSON.stringify(data);
        if (silent && payloadKey === lastPayloadKey) {
            return;
        }
        lastPayloadKey = payloadKey;

        document.getElementById('dashboard-qc-loading').classList.add('d-none');
        document.getElementById('dashboard-qc-error').classList.add('d-none');

        if (!data.qc_checked) {
            destroyTable();
            document.getElementById('dashboard-qc-content').classList.add('d-none');
            return;
        }

        var summaryEl = document.getElementById('dashboard-qc-summary');
        if (summaryEl) {
            summaryEl.innerHTML = summaryHtml(data);
        }

        var conf = panelConfig(panel);
        var previousPage = silent && dataTableInstance ? dataTableInstance.page() : 0;
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
        if (previousPage) {
            dataTableInstance.page(Math.min(previousPage, Math.max(0, dataTableInstance.page.info().pages - 1))).draw('page');
        }

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

    function loadFromUrl(url, panel, silent) {
        // See dashboard_table_panel.js loadFromUrl for why this guard is needed:
        // it drops responses that arrive after a newer folder has been requested.
        var requestFolderId = panel.getAttribute('data-folder-id');
        if (!silent) {
            showLoading();
        }
        return fetch(url, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Could not load QC information (' + response.status + ')');
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
        lastPayloadKey = null;
        return loadFromUrl(url, panel);
    }

    function refresh() {
        var panel = document.getElementById('dashboard-qc-panel');
        if (!panel || !panel.getAttribute('data-qc-url')) {
            return;
        }
        return loadFromUrl(panel.getAttribute('data-qc-url'), panel, true);
    }

    window.OspreyDashboardQc = {
        loadFromPanel: loadFromPanel,
        loadForFolder: loadForFolder,
        refresh: refresh
    };
}());
