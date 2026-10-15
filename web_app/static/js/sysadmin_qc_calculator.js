(function () {
    'use strict';

    // Mirrors osprey/services/qc.py:folder_passes_qc. Critical issues are a
    // hard gate checked alone against the critical threshold. Major and
    // minor issues are blended into one weighted rate (minor weighted less
    // punishing than major) and compared against the weighted rate threshold.

    function fieldValue(id) {
        var el = document.getElementById(id);
        return el ? parseFloat(el.value) || 0 : 0;
    }

    function renderCheck(prefix, issues, sampleSize, limit) {
        var pct = sampleSize > 0 ? (issues / sampleSize * 100) : 0;
        document.getElementById('qc-calc-' + prefix + '-n').textContent = issues;
        document.getElementById('qc-calc-' + prefix + '-pct').textContent = pct.toFixed(2) + '%';
        document.getElementById('qc-calc-' + prefix + '-limit').textContent = limit + '%';
        var passes = pct <= limit;
        var resultEl = document.getElementById('qc-calc-' + prefix + '-result');
        resultEl.textContent = passes ? 'Pass' : 'Fail';
        resultEl.className = passes ? 'text-success fw-semibold' : 'text-danger fw-semibold';
        return passes;
    }

    function recalc(form) {
        var sampleSize = fieldValue('qc-calc-sample');
        var critical = fieldValue('qc-calc-critical');
        var major = fieldValue('qc-calc-major');
        var minor = fieldValue('qc-calc-minor');
        var limitCritical = parseFloat(form.getAttribute('data-threshold-critical')) || 0;
        var wMajor = parseFloat(form.getAttribute('data-w-major')) || 0;
        var wMinor = parseFloat(form.getAttribute('data-w-minor')) || 0;
        var limitWeighted = parseFloat(form.getAttribute('data-weighted-rate')) || 0;
        var conclusionEl = document.getElementById('qc-calc-conclusion');

        if (sampleSize <= 0) {
            conclusionEl.textContent = 'enter a sample size';
            conclusionEl.className = 'badge bg-secondary';
            return;
        }

        var okCritical = renderCheck('critical', critical, sampleSize, limitCritical);
        var weightedIssues = major * wMajor + minor * wMinor;
        var okWeighted = renderCheck('weighted', weightedIssues, sampleSize, limitWeighted);
        var passes = okCritical && okWeighted;
        conclusionEl.textContent = passes ? 'PASS' : 'FAIL';
        conclusionEl.className = passes ? 'badge bg-success' : 'badge bg-danger';
    }

    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('qc-calculator');
        if (!form) {
            return;
        }
        form.addEventListener('input', function () { recalc(form); });
        recalc(form);
    });
}());
