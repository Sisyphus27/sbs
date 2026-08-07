(function () {
  var el = document.getElementById('legal-map');
  var lm = document.getElementById('new-load-model');
  var mode = document.getElementById('new-mode');
  var startLabel = document.querySelector('[data-new-start-label]');
  if (!el || !lm || !mode) return;
  var LEGAL = JSON.parse(el.textContent);

  function setFields(selector, enabled) {
    document.querySelectorAll(selector).forEach(function (field) {
      field.hidden = !enabled;
      field.querySelectorAll('input, select').forEach(function (control) {
        control.disabled = !enabled;
      });
    });
  }

  function syncFields() {
    var isLinear = mode.value === 'linear_t2' || mode.value === 'linear_t3';
    setFields('[data-sbs-field]', mode.value === 'sbs');
    setFields('[data-linear-field]', isLinear);
    setFields('[data-bodyweight-field]', lm.value !== 'barbell');
    if (startLabel) {
      startLabel.textContent = lm.value === 'barbell'
        ? startLabel.dataset.workingLabel
        : startLabel.dataset.addedLabel;
    }
  }

  function sync() {
    var allowed = LEGAL[lm.value] || [];
    mode.innerHTML = '';
    allowed.forEach(function (m) {
      var o = document.createElement('option');
      o.value = m; o.textContent = m;
      mode.appendChild(o);
    });
    syncFields();
  }
  lm.addEventListener('change', sync);
  mode.addEventListener('change', syncFields);
  sync();
})();

(function () {
  document.querySelectorAll('form[data-disable-submit]').forEach(function (form) {
    form.addEventListener('submit', function () {
      form.querySelectorAll('[type="submit"]').forEach(function (button) {
        button.disabled = true;
      });
    });
  });
})();

(function () {
  var workspace = document.querySelector('[data-week-settlement]');
  if (!workspace) return;
  var form = workspace.querySelector('form[data-disable-submit]');
  var review = document.getElementById('settlement-review');
  var handled = workspace.querySelector('[data-handled-count]');
  var pending = workspace.querySelector('[data-pending-count]');
  var next = workspace.querySelector('[data-next-unresolved]');

  function rows() {
    return Array.prototype.slice.call(
      workspace.querySelectorAll('.week-ledger-row')
    );
  }

  function rowState(row) {
    if (row.dataset.requestFailed === 'true') return 'unresolved';
    var status = row.querySelector('[data-ledger-status]');
    if (status && status.classList.contains('is-logged')) return 'logged';
    if (row.dataset.skipped === 'true') return 'skipped';
    return 'unresolved';
  }

  function syncRow(row) {
    var state = rowState(row);
    var requestPending = Number(row.dataset.pendingRequests || 0) > 0;
    if (state === 'logged' && row.dataset.skipped === 'true') {
      row.dataset.skipped = 'false';
      row.querySelector('[name="skipped_slot_ids"]').disabled = true;
      row.querySelectorAll('input:not([name="skipped_slot_ids"])').forEach(
        function (input) { input.disabled = false; }
      );
    }
    row.dataset.settlementState = state;
    row.classList.toggle('is-skipped', state === 'skipped');
    row.classList.toggle('is-logged', state === 'logged');
    row.classList.toggle('is-unresolved', state === 'unresolved');
    var toggle = row.querySelector('[data-skip-toggle]');
    if (toggle) {
      toggle.hidden = state === 'logged';
      toggle.disabled = state === 'logged' || requestPending;
      if (state === 'logged') toggle.textContent = '本周跳过';
    }
  }

  function syncWorkspace() {
    var allRows = rows();
    allRows.forEach(syncRow);
    var handledCount = allRows.filter(function (row) {
      return rowState(row) !== 'unresolved';
    }).length;
    var hasPendingRequest = allRows.some(function (row) {
      return Number(row.dataset.pendingRequests || 0) > 0;
    });
    handled.textContent = handledCount;
    pending.textContent = allRows.length - handledCount;
    review.disabled = handledCount !== allRows.length || hasPendingRequest;
    next.disabled = handledCount === allRows.length;
  }

  workspace.querySelectorAll('[data-skip-toggle]').forEach(function (toggle) {
    toggle.addEventListener('click', function () {
      var row = toggle.closest('.week-ledger-row');
      var skipping = row.dataset.skipped !== 'true';
      row.dataset.skipped = skipping ? 'true' : 'false';
      row.dataset.requestFailed = 'false';
      var hidden = row.querySelector('[name="skipped_slot_ids"]');
      hidden.disabled = !skipping;
      row.querySelectorAll('input:not([name="skipped_slot_ids"])').forEach(
        function (input) { input.disabled = skipping; }
      );
      var status = row.querySelector('[data-ledger-status]');
      status.className = 'ledger-status ' + (
        skipping ? 'is-skipped' : 'is-unresolved'
      );
      status.textContent = skipping ? '本周跳过' : '待处理';
      toggle.textContent = skipping ? '恢复补录' : '本周跳过';
      toggle.value = skipping ? 'skip' : 'focus';
      if (window.htmx) window.htmx.trigger(toggle, 'settlement-preview');
      syncWorkspace();
    });
  });

  next.addEventListener('click', function () {
    var row = rows().find(function (candidate) {
      return rowState(candidate) === 'unresolved';
    });
    if (!row) return;
    row.scrollIntoView({behavior: 'smooth', block: 'center'});
    var focus = row.querySelector('.focus-lift');
    if (focus) focus.click();
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    var row = event.detail.elt.closest('.week-ledger-row');
    if (!row) return;
    row.dataset.pendingRequests = String(
      Number(row.dataset.pendingRequests || 0) + 1
    );
    row.dataset.requestFailed = 'false';
    syncWorkspace();
  });
  document.body.addEventListener('htmx:afterRequest', function (event) {
    var row = event.detail.elt.closest('.week-ledger-row');
    if (!row) return;
    row.dataset.pendingRequests = String(Math.max(
      0, Number(row.dataset.pendingRequests || 0) - 1
    ));
    row.dataset.requestFailed = event.detail.successful ? 'false' : 'true';
    if (!event.detail.successful) {
      var status = row.querySelector('[data-ledger-status]');
      status.className = 'ledger-status is-unresolved';
      status.textContent = '保存失败 · 待处理';
    }
    window.setTimeout(syncWorkspace, 0);
  });
  document.body.addEventListener('htmx:afterSettle', syncWorkspace);
  syncWorkspace();
})();
