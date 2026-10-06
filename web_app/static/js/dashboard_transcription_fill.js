/**
 * Dashboard panel: per-field fill rate for the selected transcription folder.
 * Reads the nightly results from /api/folders/<id>/transcription_fill and
 * renders one collapsible accordion item per source, styled like the QC panels
 * (see dashboard_transcription_qc.js). Hidden until the folder has results.
 */
(function () {
    'use strict';

    var dataTableInstances = [];

    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function sourceDomId(sourceId) {
        return String(sourceId || 'source').replace(/[^A-Za-z0-9_-]/g, '_');
    }

    // Same stacked bar as the report page (filled / nonstring / empty).
    function barHtml(field) {
        return '<div class="progress-stacked" aria-hidden="true">' +
            '<div class="progress" style="width:' + field.filled_pct + '%"><div class="progress-bar bg-success"></div></div>' +
            '<div class="progress" style="width:' + field.nonstring_pct + '%"><div class="progress-bar bg-warning"></div></div>' +
            '<div class="progress" style="width:' + field.empty_pct + '%"><div class="progress-bar bg-secondary bg-opacity-25"></div></div>' +
            '</div>';
    }

    function buildTableDom(source) {
        var thead = '<thead><tr>' +
            '<th scope="col">Field</th>' +
            '<th scope="col" class="no-export">Distribution</th>' +
            '<th scope="col">Filled %</th>' +
            '<th scope="col">NonString %</th>' +
            '<th scope="col">Empty %</th>' +
            '</tr></thead>';
        var bodyRows = (source.fields || []).map(function (field) {
            return '<tr>' +
                '<td>' + escapeHtml(field.field_name) + '</td>' +
                '<td class="w-50">' + barHtml(field) + '</td>' +
                '<td>' + field.filled_pct + '</td>' +
                '<td>' + field.nonstring_pct + '</td>' +
                '<td>' + field.empty_pct + '</td>' +
                '</tr>';
        }).join('');
        return thead + '<tbody>' + bodyRows + '</tbody>';
    }

    function filesLabel(count) {
        var n = parseInt(count, 10) || 0;
        return n + ' transcribed file' + (n === 1 ? '' : 's');
    }

    function buildSourceItem(source, reportUrl) {
        var domId = sourceDomId(source.source_id);
        var headingId = 'transcription_fill_heading_' + domId;
        var panelId = 'transcription_fill_panel_' + domId;
        var tableId = 'transcription_fill_table_' + domId;
        var link = reportUrl + '?source_id=' + encodeURIComponent(source.source_id);

        return '<div class="accordion-item">' +
            '<h2 class="accordion-header" id="' + headingId + '">' +
                '<button class="accordion-button collapsed" type="button" ' +
                        'data-bs-toggle="collapse" data-bs-target="#' + panelId + '" ' +
                        'aria-expanded="false" aria-controls="' + panelId + '">' +
                    'Transcription Field Fill Rate - ' + escapeHtml(source.source_name) + ' (click to expand)' +
                    // Shared denominator for all fields, shown once instead of a per-row column.
                    '<span class="badge bg-secondary ms-2">' + filesLabel(source.total_files) + '</span>' +
                '</button>' +
            '</h2>' +
            '<div id="' + panelId + '" class="accordion-collapse collapse" ' +
                 'aria-labelledby="' + headingId + '" data-bs-parent="#transcription_fill_accordion">' +
                '<div class="accordion-body">' +
                    '<p class="small text-muted mb-2">Percentages are of ' + filesLabel(source.total_files) +
                        ' in this folder | Computed ' + escapeHtml(source.computed_at) +
                        ' | <a href="' + escapeHtml(link) + '">Full transcription profile</a></p>' +
                    '<table id="' + tableId + '" class="display compact table-striped w-100">' +
                        buildTableDom(source) +
                    '</table>' +
                '</div>' +
            '</div>' +
        '</div>';
    }

    function destroyTables() {
        dataTableInstances.forEach(function (instance) {
            instance.destroy();
        });
        dataTableInstances = [];
    }

    function initializeTables(sources) {
        (sources || []).forEach(function (source) {
            var $table = $('#transcription_fill_table_' + sourceDomId(source.source_id));
            if ($table.length) {
                dataTableInstances.push($table.DataTable({
                    dom: 'Bfrtip',
                    // The bar column is visual only; exports get the numbers.
                    buttons: [
                        { extend: 'csvHtml5', exportOptions: { columns: ':not(.no-export)' } },
                        { extend: 'excelHtml5', exportOptions: { columns: ':not(.no-export)' } }
                    ],
                    order: [],
                    columnDefs: [
                        { targets: 0, createdCell: function (td) { $(td).attr('scope', 'row'); } },
                        { targets: 1, orderable: false, searchable: false }
                    ],
                    lengthMenu: [[25, 50, 100, -1], [25, 50, 100, 'All']]
                }));
            }
        });
    }

    // DataTables measures columns while hidden; re-measure once a panel opens.
    function bindAccordionAdjust() {
        var accordion = document.getElementById('transcription_fill_accordion');
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

    function render(panel, data) {
        var accordion = document.getElementById('transcription_fill_accordion');
        var sources = data.sources || [];
        destroyTables();
        accordion.innerHTML = '';
        if (!sources.length) {
            panel.classList.add('d-none');
            return;
        }
        var reportUrl = panel.getAttribute('data-report-url') || '';
        accordion.innerHTML = sources.map(function (s) { return buildSourceItem(s, reportUrl); }).join('');
        initializeTables(sources);
        bindAccordionAdjust();
        panel.classList.remove('d-none');
    }

    function loadFromUrl(url, panel) {
        // Drop responses for a folder the user has already navigated away from
        // (see dashboard_table_panel.js loadFromUrl).
        var requestFolderId = panel.getAttribute('data-folder-id');
        return fetch(url, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                if (panel.getAttribute('data-folder-id') === requestFolderId) {
                    render(panel, data);
                }
            })
            .catch(function (error) {
                // Optional panel: hide it rather than show an error block.
                if (panel.getAttribute('data-folder-id') === requestFolderId) {
                    panel.classList.add('d-none');
                }
                console.error('dashboard_transcription_fill:', error);
            });
    }

    function loadFromPanel() {
        var panel = document.getElementById('dashboard-transcription-fill-panel');
        if (!panel || !panel.getAttribute('data-fill-url')) {
            return;
        }
        return loadFromUrl(panel.getAttribute('data-fill-url'), panel);
    }

    function loadForFolder(folderId) {
        var panel = document.getElementById('dashboard-transcription-fill-panel');
        if (!panel) {
            return;
        }
        var url = (panel.getAttribute('data-api-path') || '/api/folders/') +
            encodeURIComponent(folderId) + '/transcription_fill';
        panel.setAttribute('data-fill-url', url);
        panel.setAttribute('data-folder-id', String(folderId));
        return loadFromUrl(url, panel);
    }

    window.OspreyDashboardTranscriptionFill = {
        loadFromPanel: loadFromPanel,
        loadForFolder: loadForFolder
    };
}());
