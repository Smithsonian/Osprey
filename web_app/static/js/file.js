/**
 * File detail page: tabs, modals, metadata table, keyboard navigation.
 */
(function () {
  'use strict';

  var TAB_TARGETS = {
    checks: '#file-tab-checks-btn',
    post: '#file-tab-post-btn',
    metadata: '#file-tab-metadata-btn',
    links: '#file-tab-links-btn'
  };

  function isEditableTarget(el) {
    if (!el || !el.tagName) {
      return false;
    }
    var tag = el.tagName.toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable;
  }

  function showTab(tabKey) {
    var selector = TAB_TARGETS[tabKey];
    if (!selector) {
      return;
    }
    var btn = document.querySelector(selector);
    if (btn && window.bootstrap && window.bootstrap.Tab) {
      window.bootstrap.Tab.getOrCreateInstance(btn).show();
    }
  }

  function initModals() {
    var checkModal = document.getElementById('checkmodal');
    if (checkModal) {
      checkModal.addEventListener('show.bs.modal', function (event) {
        var button = event.relatedTarget;
        var checkinfo = button.getAttribute('data-bs-info');
        var modalBody = checkModal.querySelector('.modal-body pre');
        if (modalBody) {
          modalBody.textContent = checkinfo || '';
        }
      });
    }

    var postModal = document.getElementById('postmodal');
    if (postModal) {
      postModal.addEventListener('show.bs.modal', function (event) {
        var button = event.relatedTarget;
        var postinfo = button.getAttribute('data-bs-info2');
        var modalBody = postModal.querySelector('.modal-body pre');
        if (modalBody) {
          modalBody.textContent = postinfo || '';
        }
      });
    }
  }

  function initMetadataTable() {
    var table = document.getElementById('file_metadata');
    if (!table || !window.jQuery || !jQuery.fn.DataTable) {
      return;
    }

    var dataTable = jQuery(table).DataTable({
      dom: 'Bfrtip',
      buttons: ['csvHtml5', 'excelHtml5'],
      order: [],
      columnDefs: [{
        targets: 0,
        createdCell: function (td) {
          jQuery(td).attr('scope', 'row');
        }
      }],
      lengthMenu: [[25, 50, 100, -1], [25, 50, 100, 'All']]
    });

    var metadataTab = document.getElementById('file-tab-metadata-btn');
    if (metadataTab) {
      metadataTab.addEventListener('shown.bs.tab', function () {
        dataTable.columns.adjust().draw(false);
      });
    }
  }

  function initStatusChipTabs() {
    document.querySelectorAll('[data-file-tab]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        showTab(chip.getAttribute('data-file-tab'));
        document.getElementById('file-details-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  function initKeyboardNav() {
    var page = document.getElementById('file-page');
    if (!page) {
      return;
    }

    var prevUrl = page.getAttribute('data-prev-url');
    var nextUrl = page.getAttribute('data-next-url');

    document.addEventListener('keydown', function (event) {
      if (isEditableTarget(event.target)) {
        return;
      }
      if (event.key === 'ArrowLeft' && prevUrl) {
        window.location.href = prevUrl;
      } else if (event.key === 'ArrowRight' && nextUrl) {
        window.location.href = nextUrl;
      }
    });
  }

  function initDefaultTab() {
    var hash = window.location.hash.replace('#', '');
    if (hash && TAB_TARGETS[hash]) {
      showTab(hash);
      return;
    }

    var page = document.getElementById('file-page');
    if (!page) {
      return;
    }

    if (page.getAttribute('data-has-check-failures') === '1') {
      showTab('checks');
    } else if (page.getAttribute('data-has-post-failures') === '1') {
      showTab('post');
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    initModals();
    initMetadataTable();
    initStatusChipTabs();
    initKeyboardNav();
    initDefaultTab();
  });
})();
