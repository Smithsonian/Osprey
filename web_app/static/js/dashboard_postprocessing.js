(function () {
    'use strict';

    window.OspreyDashboardPostprocessing = window.OspreyDashboardTablePanel.create({
        idPrefix: 'dashboard-postprod',
        panelId: 'dashboard-postprod-panel',
        tableId: 'post_processing_table',
        filterKey: 'postprod-filter',
        filterNamespace: 'dashboardPostprod',
        itemsKey: 'file_postprocessing',
        nameKey: 'post_step',
        resultKey: 'post_results',
        columnsKey: 'project_postprocessing',
        errorNoun: 'post-processing steps',
        badgeClass: {
            Completed: 'file-result-badge file-result-badge--ok',
            Failed: 'file-result-badge file-result-badge--failed',
            Pending: 'file-result-badge file-result-badge--pending'
        }
    });
}());
