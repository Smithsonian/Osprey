(function () {
    'use strict';

    // Mirrors osprey/services/qc.py:_checks for the project's qc_method.
    // weighted: critical issues are a hard gate checked alone against the
    // critical threshold; major and minor issues are blended into one
    // weighted rate (minor weighted less punishing than major) and compared
    // against the weighted rate threshold.
    // cumulative: critical, critical + major and critical + major + minor
    // are checked against the critical, major and minor thresholds.

    function fieldValue(id) {
        var el = document.getElementById(id);
        return el ? parseFloat(el.value) || 0 : 0;
    }

    function attr(form, name) {
        return parseFloat(form.getAttribute(name)) || 0;
    }

    function checks(form, critical, major, minor) {
        var list = [['Critical', critical, attr(form, 'data-threshold-critical')]];
        if (form.getAttribute('data-qc-method') === 'cumulative') {
            list.push(['Critical + major', critical + major, attr(form, 'data-threshold-major')]);
            list.push(['Critical + major + minor', critical + major + minor, attr(form, 'data-threshold-minor')]);
        } else {
            var weighted = major * attr(form, 'data-w-major') + minor * attr(form, 'data-w-minor');
            list.push(['Weighted major + minor', weighted, attr(form, 'data-weighted-rate')]);
        }
        return list;
    }

    function cell(tag, text, className) {
        var el = document.createElement(tag);
        el.textContent = text;
        if (tag === 'th') {
            el.scope = 'row';
        }
        if (className) {
            el.className = className;
        }
        return el;
    }

    function recalc(form) {
        var sampleSize = fieldValue('qc-calc-sample');
        var tbody = document.getElementById('qc-calc-checks');
        var conclusionEl = document.getElementById('qc-calc-conclusion');
        tbody.textContent = '';

        if (sampleSize <= 0) {
            conclusionEl.textContent = 'enter a sample size';
            conclusionEl.className = 'badge bg-secondary';
            return;
        }

        var passes = true;
        checks(form, fieldValue('qc-calc-critical'), fieldValue('qc-calc-major'),
            fieldValue('qc-calc-minor')).forEach(function (check) {
            var pct = check[1] / sampleSize * 100;
            var ok = pct <= check[2];
            passes = passes && ok;
            var row = document.createElement('tr');
            row.appendChild(cell('th', check[0]));
            row.appendChild(cell('td', Math.round(check[1] * 1000) / 1000));
            row.appendChild(cell('td', pct.toFixed(2) + '%'));
            row.appendChild(cell('td', check[2] + '%'));
            row.appendChild(cell('td', ok ? 'Pass' : 'Fail',
                ok ? 'text-success fw-semibold' : 'text-danger fw-semibold'));
            tbody.appendChild(row);
        });
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
