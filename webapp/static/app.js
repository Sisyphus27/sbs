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
  var snapshotElement = document.getElementById('week-workspace-snapshot');
  if (!workspace || !snapshotElement || !window.createWeekWorkspace) return;
  var snapshot = JSON.parse(snapshotElement.textContent);
  var expectedWeek = snapshot.expectedWeek;
  var handle = window.createWeekWorkspace(snapshot);
  var review = document.getElementById('settlement-review');
  var handled = workspace.querySelector('[data-handled-count]');
  var pending = workspace.querySelector('[data-pending-count]');
  var next = workspace.querySelector('[data-next-unresolved]');

  function rowFor(slotId) {
    return document.getElementById('ledger-row-' + slotId);
  }

  function renderWorkspace(effect) {
    effect.view.lifts.forEach(function (lift) {
      var row = rowFor(lift.slotId);
      if (!row) return;
      row.classList.toggle('is-skipped', lift.state === 'skipped');
      row.classList.toggle('is-logged', lift.state === 'logged');
      row.classList.toggle('is-unresolved', lift.state === 'unresolved');

      var status = row.querySelector('[data-ledger-status]');
      if (status) {
        status.className = 'ledger-status ' + (
          lift.state === 'logged' ? 'is-logged' :
            lift.state === 'skipped' ? 'is-skipped' : 'is-unresolved'
        );
        if (lift.failedZero) status.classList.add('is-zero');
        status.textContent = lift.saving ? '保存中 · 待处理' :
          lift.error ? '保存失败 · 待处理' :
            lift.failedZero ? '已补录 · 0 次失败' :
              lift.state === 'logged' ? '已补录' :
                lift.state === 'skipped' ? '本周跳过' : '待处理';
      }

      var error = row.querySelector('[data-workspace-error]');
      if (error) error.textContent = lift.error || '';
      var skippedInput = row.querySelector('[name="skipped_slot_ids"]');
      if (skippedInput) skippedInput.disabled = lift.state !== 'skipped';
      row.querySelectorAll('input[data-week-field]').forEach(function (input) {
        input.disabled = lift.state === 'skipped';
      });

      var skip = row.querySelector('[data-skip-lift]');
      var resume = row.querySelector('[data-resume-lift]');
      if (skip) {
        skip.hidden = lift.state === 'logged'
          || lift.settlementIntent === 'skip';
        skip.disabled = lift.state === 'logged';
      }
      if (resume) {
        resume.hidden = lift.state === 'logged'
          || lift.settlementIntent !== 'skip';
        resume.disabled = lift.state === 'logged';
      }
    });
    handled.textContent = effect.view.handled;
    pending.textContent = effect.view.pending;
    review.disabled = !effect.view.reviewEligible;
    next.disabled = effect.view.nextUnresolvedSlotId === null;
  }

  function replaceTopLevelElements(fragment) {
    var container = document.createElement('template');
    container.innerHTML = fragment.trim();
    Array.prototype.slice.call(container.content.children).forEach(
      function (replacement) {
        if (!replacement.id) return;
        var current = document.getElementById(replacement.id);
        if (current) current.replaceWith(replacement);
      }
    );
  }

  function renderInspector(fragment) {
    var container = document.createElement('template');
    container.innerHTML = fragment.trim();
    var replacement = container.content.firstElementChild;
    var current = document.getElementById('focus-inspector');
    if (current && replacement) current.replaceWith(replacement);
  }

  function renderInspectorError(message) {
    var current = document.getElementById('focus-inspector');
    if (!current) return;
    var error = document.createElement('div');
    error.className = 'flash flash-error';
    error.textContent = message;
    current.textContent = '';
    current.appendChild(error);
  }

  function renderReload() {
    workspace.querySelectorAll('button, input').forEach(function (control) {
      control.disabled = true;
    });
    var instruction = document.createElement('div');
    instruction.className = 'flash flash-error';
    instruction.textContent = 'Program week 已变更，请重新加载页面。';
    workspace.insertBefore(instruction, workspace.firstChild);
  }

  function executeEffects(effects) {
    effects.forEach(function (effect) {
      if (effect.type === 'request') {
        sendRequest(effect);
      } else if (effect.role === 'workspace') {
        renderWorkspace(effect);
      } else if (effect.role === 'persistent') {
        replaceTopLevelElements(effect.fragment);
      } else if (effect.role === 'inspector') {
        if (effect.fragment) {
          renderInspector(effect.fragment);
        } else if (effect.error) {
          renderInspectorError(effect.error);
        }
      } else if (effect.role === 'reload') {
        renderReload();
      }
    });
  }

  function responseEnvelope(responseText) {
    var parsed = new DOMParser().parseFromString(responseText, 'text/html');
    var envelope = parsed.querySelector('template[data-week-workspace-response]');
    if (!envelope) return null;
    var snapshotScript = envelope.content.querySelector(
      'script[data-server-snapshot]'
    );
    function fragment(role) {
      var child = envelope.content.querySelector(
        'template[data-fragment-role="' + role + '"]'
      );
      return child ? child.innerHTML.trim() : undefined;
    }
    return {
      role: envelope.dataset.responseRole,
      expectedWeek: Number(envelope.dataset.expectedWeek),
      slotId: Number(envelope.dataset.slotId),
      saveSequence: Number(envelope.dataset.saveSequence),
      focusedSlotId: Number(envelope.dataset.focusedSlotId),
      focusSequence: Number(envelope.dataset.focusSequence),
      serverSnapshot: snapshotScript
        ? JSON.parse(snapshotScript.textContent) : undefined,
      persistentFragment: fragment('persistent'),
      inspectorFragment: fragment('inspector'),
    };
  }

  function resultEvent(effect, xhr) {
    var payload = effect.payload;
    var successful = xhr.status >= 200 && xhr.status < 300;
    var envelope = successful ? responseEnvelope(xhr.responseText) : null;
    if (successful && (!envelope || envelope.role !== effect.role)) {
      successful = false;
    }
    var identity = envelope || payload;
    var event = {
      type: effect.role === 'save' ? 'saveResult' : 'inspectorResult',
      expectedWeek: identity.expectedWeek,
      slotId: identity.slotId,
      focusSequence: identity.focusSequence,
      success: successful,
      staleWeek: xhr.status === 409,
    };
    if (effect.role === 'save') {
      event.saveSequence = identity.saveSequence;
      event.focusedSlotId = identity.focusedSlotId;
      if (envelope && envelope.serverSnapshot) {
        event.serverSnapshot = envelope.serverSnapshot;
        event.coverage = envelope.serverSnapshot.coverage;
      }
      if (envelope && envelope.persistentFragment !== undefined) {
        event.persistentFragment = envelope.persistentFragment;
      }
    }
    if (envelope && envelope.inspectorFragment !== undefined) {
      event.inspectorFragment = envelope.inspectorFragment;
    }
    if (!successful) {
      event.error = xhr.responseText && xhr.responseText.trim()
        ? xhr.responseText.trim() : '请求失败';
    }
    return event;
  }

  function transportFailureEvent(effect) {
    var payload = effect.payload;
    return {
      type: effect.role === 'save' ? 'saveResult' : 'inspectorResult',
      expectedWeek: payload.expectedWeek,
      slotId: payload.slotId,
      saveSequence: payload.saveSequence,
      focusedSlotId: payload.focusedSlotId,
      focusSequence: payload.focusSequence,
      success: false,
      error: '请求失败',
    };
  }

  function sendRequest(effect) {
    var payload = effect.payload;
    var row = rowFor(payload.slotId);
    var source = document.createElement('span');
    source.hidden = true;
    workspace.appendChild(source);
    var url;
    var values = {
      expected_week: payload.expectedWeek,
      slot_id: payload.slotId,
      focus_sequence: payload.focusSequence,
    };
    if (effect.role === 'save') {
      url = row.dataset.saveUrl + '&set_number=' + payload.setNumber;
      values.save_sequence = payload.saveSequence;
      values.focused_slot_id = payload.focusedSlotId;
      values.set_number = payload.setNumber;
      values.reps = payload.reps;
      if (Object.prototype.hasOwnProperty.call(payload, 'actualAddedWeight')) {
        values.actual_added_weight = payload.actualAddedWeight;
      }
    } else {
      url = row.dataset.inspectorUrl;
      values.intent = payload.intent === 'skip' ? 'skip' : 'focus';
      if (Object.prototype.hasOwnProperty.call(payload, 'actualAddedWeight')) {
        values.actual_added_weight = payload.actualAddedWeight;
        values.reps = payload.driverReps;
      }
    }
    var completed = false;
    window.htmx.ajax('POST', url, {
      source: source,
      values: values,
      handler: function (_source, responseInfo) {
        completed = true;
        executeEffects(handle(resultEvent(effect, responseInfo.xhr)));
      },
    }).then(function () {
      source.remove();
    }, function () {
      if (!completed) {
        executeEffects(handle(transportFailureEvent(effect)));
      }
      source.remove();
    });
  }

  workspace.addEventListener('change', function (event) {
    var input = event.target.closest('input[data-week-field]');
    if (!input) return;
    var row = input.closest('.week-ledger-row');
    executeEffects(handle({
      type: 'change',
      expectedWeek: expectedWeek,
      slotId: Number(row.dataset.slotId),
      field: input.dataset.weekField,
      setNumber: Number(input.dataset.setNumber),
      value: input.value,
    }));
  });

  workspace.addEventListener('click', function (event) {
    var target = event.target;
    var row = target.closest('.week-ledger-row');
    if (target.closest('[data-next-unresolved]')) {
      executeEffects(handle({
        type: 'nextUnresolved', expectedWeek: expectedWeek,
      }));
    } else if (row && target.closest('[data-focus-lift]')) {
      executeEffects(handle({
        type: 'focus',
        expectedWeek: expectedWeek,
        slotId: Number(row.dataset.slotId),
      }));
    } else if (row && target.closest('[data-skip-lift]')) {
      executeEffects(handle({
        type: 'skip',
        expectedWeek: expectedWeek,
        slotId: Number(row.dataset.slotId),
      }));
    } else if (row && target.closest('[data-resume-lift]')) {
      executeEffects(handle({
        type: 'resume',
        expectedWeek: expectedWeek,
        slotId: Number(row.dataset.slotId),
      }));
    }
  });

  executeEffects(handle({type: 'bootstrap', expectedWeek: expectedWeek}));
})();
