/**
 * Render Chart.js figures from data-chart-spec JSON.
 * Supports categorical and time-series x axes (x_scale: "time").
 */
(function () {
    'use strict';

    function prefersReducedMotion() {
        return window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function parseSpec(canvas) {
        var raw = canvas.getAttribute('data-chart-spec');
        if (!raw) {
            return null;
        }
        try {
            return JSON.parse(raw);
        } catch (err) {
            console.error('statistics_charts: invalid chart spec', err);
            return null;
        }
    }

    function hasRenderableData(spec) {
        if (!spec) {
            return false;
        }
        if (spec.labels && spec.labels.length) {
            return true;
        }
        var datasets = spec.datasets || [];
        return datasets.some(function (dataset) {
            return dataset && dataset.data && dataset.data.length;
        });
    }

    function buildXScale(spec) {
        if (spec.x_scale === 'time') {
            return {
                type: 'time',
                time: {
                    unit: spec.time_unit || 'day',
                    tooltipFormat: 'yyyy-MM-dd',
                    displayFormats: {
                        day: 'yyyy-MM-dd',
                        week: 'yyyy-MM-dd',
                        month: 'MMM yyyy',
                        year: 'yyyy'
                    }
                },
                adapters: {
                    date: {}
                },
                ticks: {
                    autoSkip: true,
                    maxRotation: 45,
                    minRotation: 0
                },
                offset: true
            };
        }
        return {
            ticks: {
                maxRotation: 45,
                minRotation: 0
            }
        };
    }

    function buildConfig(spec) {
        var chartType = spec.chart_js_type || 'bar';
        var units = spec.units || '';
        var useTime = spec.x_scale === 'time';
        var data = {
            datasets: spec.datasets || []
        };
        if (!useTime) {
            data.labels = spec.labels || [];
        }
        return {
            type: chartType,
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: prefersReducedMotion() ? false : undefined,
                plugins: {
                    legend: {
                        display: (spec.datasets || []).length > 1
                    },
                    title: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            title: function (items) {
                                if (!items || !items.length) {
                                    return '';
                                }
                                var item = items[0];
                                if (useTime && item.raw && item.raw.x != null) {
                                    return String(item.raw.x).slice(0, 10);
                                }
                                return item.label || '';
                            },
                            label: function (context) {
                                var value = context.parsed.y;
                                if (value === null || value === undefined) {
                                    value = context.parsed;
                                }
                                var label = context.dataset.label || '';
                                var text = label ? label + ': ' + value : String(value);
                                return units ? text + ' ' + units : text;
                            }
                        }
                    }
                },
                scales: {
                    x: buildXScale(spec),
                    y: {
                        beginAtZero: true,
                        title: {
                            display: !!units,
                            text: units
                        }
                    }
                }
            }
        };
    }

    function initCharts() {
        if (typeof Chart === 'undefined') {
            console.error('statistics_charts: Chart.js is not loaded');
            return;
        }
        var canvases = document.querySelectorAll('canvas[data-chart-spec]');
        canvases.forEach(function (canvas) {
            var spec = parseSpec(canvas);
            if (!hasRenderableData(spec)) {
                return;
            }
            var chart = new Chart(canvas, buildConfig(spec));
            canvas._ospreyChart = chart;
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCharts);
    } else {
        initCharts();
    }
}());
