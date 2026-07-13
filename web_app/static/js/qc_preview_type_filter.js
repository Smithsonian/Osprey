(function () {
    'use strict';

    var filterSelect = document.getElementById('qc-preview-type-filter');
    if (!filterSelect) {
        return;
    }

    var rows = document.querySelectorAll('[data-qc-folder-row]');
    var emptyMsg = document.getElementById('qc-preview-type-empty');

    function applyFilter() {
        var mode = filterSelect.value;
        var visibleCount = 0;

        rows.forEach(function (row) {
            var previewType = row.getAttribute('data-preview-type') || '';
            var show = !mode || previewType === mode;
            row.classList.toggle('d-none', !show);
            if (show) {
                visibleCount += 1;
            }
        });

        if (emptyMsg) {
            var showEmpty = Boolean(mode) && visibleCount === 0;
            emptyMsg.classList.toggle('d-none', !showEmpty);
        }
    }

    filterSelect.addEventListener('change', applyFilter);
})();
