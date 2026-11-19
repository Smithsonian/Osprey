(function () {
    'use strict';

    var TRANSCRIPTION_QC_BADGE = {
        0: '<span class="badge text-bg-success">Transcription OK</span>',
        1: '<span class="badge text-bg-danger">Critical Issue</span>',
        2: '<span class="badge text-bg-warning">Major Issue</span>',
        3: '<span class="badge text-bg-warning">Minor Issue</span>',
        9: '<span class="badge text-bg-secondary">Pending</span>'
    };

    var dataTableInstances = [];
    var lastPayloadKey = null;

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
        return '<a href="' + path + '" title="File Details">' +
            escapeHtml(file.file_name) + '</a>';
    }

    function statusBadge(statusValue) {
        if (parseInt(statusValue, 10) === 0) {
            return '<span class="badge text-bg-success">Passed</span>';
        }
        if (parseInt(statusValue, 10) === 1) {
            return '<span class="badge text-bg-danger">Failed</span>';
        }
        return '<span class="badge text-bg-warning">Pending</span>';
    }

    function plural(n, word) {
        return n + ' ' + word + (n === 1 ? '' : 's');
    }

    // "25 files sampled · 2 critical, 1 minor · 3 pending" for the button.
    function summaryDetail(source) {
        var files = source.files || [];
        var counts = { 0: 0, 1: 0, 2: 0, 3: 0, 9: 0 };
        files.forEach(function (file) {
            var value = parseInt(file.qc_results, 10);
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
            parts.push(counts[9] + ' pending');
        }
        return parts.join(' · ');
    }

    function openPanelIds(accordion) {
        return Array.prototype.map.call(accordion.querySelectorAll('.accordion-collapse.show'), function (el) {
            return el.id;
        });
    }

    // Re-open the items that were open before a background refresh redrew them.
    function reopenPanels(accordion, ids) {
        ids.forEach(function (id) {
            var collapseEl = document.getElementById(id);
            if (!collapseEl || !accordion.contains(collapseEl)) {
                return;
            }
            collapseEl.classList.add('show');
            var button = accordion.querySelector('[data-bs-target="#' + id + '"]');
            if (button) {
                button.classList.remove('collapsed');
                button.setAttribute('aria-expanded', 'true');
            }
        });
    }


    function destroyTables() {
        dataTableInstances.forEach(function (instance) {
            instance.destroy();
        });
        dataTableInstances = [];
    }

    function buildTableDom(source, appRoot) {
        var thead = '<thead><tr><th scope="col">File</th><th scope="col">QC notes</th><th scope="col">Result</th></tr></thead>';
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
            '<h3 class="accordion-header" id="' + headingId + '">' +
                '<button class="accordion-button collapsed" type="button" ' +
                        'data-bs-toggle="collapse" data-bs-target="#' + panelId + '" ' +
                        'aria-expanded="false" aria-controls="' + panelId + '">' +
                    '<span class="dashboard-qc-summary">' +
                        '<span class="fw-semibold">Transcription QC: ' +
                            escapeHtml(source.source_name || 'Source ' + (index + 1)) + '</span>' +
                        statusBadge(source.qc_status_value) +
                        '<span class="dashboard-qc-summary-detail">' + escapeHtml(summaryDetail(source)) + '</span>' +
                    '</span>' +
                '</button>' +
            '</h3>' +
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

    function showContent(data, panel, silent) {
        var payloadKey = JSON.stringify(data);
        if (silent && payloadKey === lastPayloadKey) {
            return;
        }
        lastPayloadKey = payloadKey;

        document.getElementById('dashboard-transcription-qc-loading').classList.add('d-none');
        document.getElementById('dashboard-transcription-qc-error').classList.add('d-none');

        var contentEl = document.getElementById('dashboard-transcription-qc-content');
        var accordion = document.getElementById('transcription_qc_accordion');
        var wasOpen = silent ? openPanelIds(accordion) : [];
        destroyTables();
        accordion.innerHTML = '';

        if (!data.qc_checked || !(data.sources || []).length) {
            contentEl.classList.add('d-none');
            return;
        }

        var appRoot = panel.getAttribute('data-app-root') || '';
        accordion.innerHTML = data.sources.map(function (source, index) {
            return buildSourceItem(source, index, appRoot);
        }).join('');

        reopenPanels(accordion, wasOpen);
        initializeTables(data.sources);
        bindAccordionAdjust();
        contentEl.classList.remove('d-none');
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
                    throw new Error('Could not load transcription QC information (' + response.status + ')');
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
        lastPayloadKey = null;
        return loadFromUrl(url, panel);
    }

    function refresh() {
        var panel = document.getElementById('dashboard-transcription-qc-panel');
        if (!panel || !panel.getAttribute('data-qc-url')) {
            return;
        }
        return loadFromUrl(panel.getAttribute('data-qc-url'), panel, true);
    }

    window.OspreyDashboardTranscriptionQc = {
        loadFromPanel: loadFromPanel,
        loadForFolder: loadForFolder,
        refresh: refresh
    };
}());
