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

  function initPlainTable(tableId) {
    if (!$(tableId).length) {
      return;
    }
    $(tableId).DataTable(dtOptions);
  }

  window.OspreyHomepage = {
    init: function (team) {
      if (team === 'md') {
        initPlainTable('#list_projects_md');
      } else if (team === 'is') {
        initPlainTable('#list_projects_is');
      } else if (team === 'inf') {
        initPlainTable('#list_projects_inf');
        initPlainTable('#list_software');
      }
    },
  };
}(window));
