/* global $ */
(function (window) {
  'use strict';

  var dtOptions = {
    ordering: false,
    paging: false,
    lengthChange: false,
    searching: true,
    dom: 'frt',
    language: {
      search: '',
      searchPlaceholder: 'Filter table…',
    },
  };

  function initSortableTable(tableId) {
    if (!$(tableId).length) {
      return;
    }
    var table = $(tableId).DataTable($.extend({ order: [[0, 'desc']] }, dtOptions));
    table.column(0).visible(false);
  }

  function initPlainTable(tableId) {
    if (!$(tableId).length) {
      return;
    }
    $(tableId).DataTable(dtOptions);
  }

  window.OspreyHomepage = {
    init: function () {
      initSortableTable('#list_projects_md');
      initSortableTable('#list_projects_is');
      initPlainTable('#list_projects_inf');
      initPlainTable('#list_software');
    },
  };
}(window));
