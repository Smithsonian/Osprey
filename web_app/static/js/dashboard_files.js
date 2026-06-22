(function () {
    'use strict';

    window.OspreyDashboardFiles = window.OspreyDashboardTablePanel.create({
        idPrefix: 'dashboard-files',
        panelId: 'dashboard-files-panel',
        tableId: 'files_table',
        filterKey: 'files-filter',
        filterNamespace: 'dashboardFiles',
        itemsKey: 'file_checks',
        nameKey: 'file_check',
        resultKey: 'check_results',
        columnsKey: 'project_checks',
        errorNoun: 'files',
        badgeClass: {
            OK: 'file-result-badge file-result-badge--ok',
            Failed: 'file-result-badge file-result-badge--failed',
            Pending: 'file-result-badge file-result-badge--pending'
        }
    });
}());
