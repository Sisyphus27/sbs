(function (root, factory) {
  "use strict";

  var createWeekWorkspace = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = {createWeekWorkspace: createWeekWorkspace};
  } else {
    root.createWeekWorkspace = createWeekWorkspace;
  }
}(typeof globalThis === "undefined" ? this : globalThis, function () {
  "use strict";

  // Public seam: createWeekWorkspace(snapshot) returns handle(event). Events are
  // bootstrap, change, focus, skip, resume, nextUnresolved, saveResult,
  // inspectorResult, settlementResult. Effects are request(save|inspector|settlement) and
  // render(workspace|persistent|inspector|reload); all mutable state stays here.

  function copyValue(value) {
    if (Array.isArray(value)) return value.map(copyValue);
    if (value && typeof value === "object") {
      var copy = {};
      Object.keys(value).forEach(function (name) {
        copy[name] = copyValue(value[name]);
      });
      return copy;
    }
    return value;
  }

  function slotKey(slotId) {
    return String(slotId);
  }

  function copyDraft(draft) {
    return {
      addedWeight: draft.addedWeight,
      driverReps: draft.driverReps,
      earlierSetReps: Object.assign({}, draft.earlierSetReps || {}),
    };
  }

  function isZero(value) {
    return value !== "" && value !== null && value !== undefined
      && Number(value) === 0;
  }

  function createWeekWorkspace(serverSnapshot) {
    var expectedWeek = serverSnapshot.expectedWeek;
    var order = [];
    var liftsBySlotId = Object.create(null);
    var requestsStopped = false;
    var focus = {
      slotId: serverSnapshot.focusedSlotId === undefined
        ? null
        : serverSnapshot.focusedSlotId,
      sequence: Number(serverSnapshot.focusSequence || 0),
    };

    (serverSnapshot.lifts || []).forEach(function (source) {
      var key = slotKey(source.slotId);
      var server = copyValue(source.serverSnapshot || {});
      var acceptedRevisions = Object.create(null);
      (server.coverage || []).forEach(function (path) {
        acceptedRevisions[path] = 0;
      });
      order.push(key);
      liftsBySlotId[key] = {
        slotId: source.slotId,
        driverSetNumber: source.driverSetNumber,
        draft: copyDraft(source.draft || {}),
        serverSnapshot: server,
        settlementIntent: source.settlementIntent || "record",
        intentRequest: null,
        intentError: null,
        fieldRevisions: {
          addedWeight: 0,
          driverReps: 0,
          earlierSetReps: Object.create(null),
        },
        acceptedRevisions: acceptedRevisions,
        nextSaveSequence: 0,
        queue: [],
        inFlight: null,
        lastTerminal: null,
      };
    });

    function pendingCount(lift) {
      return lift.queue.length + (lift.inFlight ? 1 : 0) + (lift.intentRequest ? 1 : 0);
    }

    function attemptAffectsSettlement(attempt) {
      return Object.prototype.hasOwnProperty.call(attempt.coverage, "driverReps");
    }

    function hasSettlementSavePending(lift) {
      return Boolean(lift.inFlight && attemptAffectsSettlement(lift.inFlight))
        || lift.queue.some(attemptAffectsSettlement);
    }

    function relevantError(lift) {
      if (lift.intentError) return lift.intentError;
      if (lift.settlementIntent !== "record" || pendingCount(lift) > 0) {
        return null;
      }
      if (lift.lastTerminal
          && lift.lastTerminal.sequence === lift.nextSaveSequence
          && lift.lastTerminal.status === "failed") {
        return lift.lastTerminal.error;
      }
      return null;
    }

    function settlementDraftIsCovered(lift) {
      if (lift.acceptedRevisions.addedWeight
          !== lift.fieldRevisions.addedWeight) return false;
      return lift.acceptedRevisions.driverReps
        === lift.fieldRevisions.driverReps;
    }

    function allDraftIsCovered(lift) {
      if (!settlementDraftIsCovered(lift)) return false;
      return Object.keys(lift.fieldRevisions.earlierSetReps).every(
        function (setNumber) {
          var path = "earlierSetReps." + setNumber;
          return lift.acceptedRevisions[path]
            === lift.fieldRevisions.earlierSetReps[setNumber];
        }
      );
    }

    function settlementState(lift) {
      if (lift.intentRequest || lift.intentError) return "unresolved";
      if (hasSettlementSavePending(lift)) return "unresolved";
      if (lift.settlementIntent === "skip") {
        return lift.serverSnapshot.hasDriverFact ? "logged" : "skipped";
      }
      if (relevantError(lift) && lift.lastTerminal.affectsSettlement) {
        return "unresolved";
      }
      return lift.serverSnapshot.settlementReady && settlementDraftIsCovered(lift)
        ? "logged"
        : "unresolved";
    }

    function nextActionableLift() {
      if (!order.length) return null;
      var focusIndex = order.indexOf(slotKey(focus.slotId));
      for (var offset = 1; offset <= order.length; offset += 1) {
        var index = (focusIndex + offset + order.length) % order.length;
        var lift = liftsBySlotId[order[index]];
        if (settlementState(lift) === "unresolved"
            && pendingCount(lift) === 0) {
          return lift;
        }
      }
      return null;
    }

    function workspaceRender() {
      var projected = order.map(function (key) {
        var lift = liftsBySlotId[key];
        var state = settlementState(lift);
        return {
          slotId: lift.slotId,
          state: state,
          failedZero: state === "logged"
            && isZero(lift.serverSnapshot.driverReps),
          saving: pendingCount(lift) > 0,
          error: relevantError(lift),
          settlementIntent: lift.settlementIntent,
          intentSaving: Boolean(lift.intentRequest),
          hasDriverFact: Boolean(lift.serverSnapshot.hasDriverFact),
        };
      });
      var handled = projected.filter(function (lift) {
        return lift.state !== "unresolved";
      }).length;
      var allSavesSettled = order.every(function (key) {
        var lift = liftsBySlotId[key];
        if (pendingCount(lift) > 0 || lift.intentError) return false;
        if (lift.settlementIntent === "skip") return true;
        return allDraftIsCovered(lift) && !relevantError(lift);
      });
      var nextLift = nextActionableLift();
      return {
        type: "render",
        role: "workspace",
        view: {
          expectedWeek: expectedWeek,
          focusedSlotId: focus.slotId,
          focusSequence: focus.sequence,
          lifts: projected,
          handled: handled,
          pending: projected.length - handled,
          nextUnresolvedSlotId: nextLift ? nextLift.slotId : null,
          reviewEligible: handled === projected.length && allSavesSettled,
        },
      };
    }

    function focusLift(lift) {
      focus = {slotId: lift.slotId, sequence: focus.sequence + 1};
    }

    function frozenSaveAttempt(lift, field, setNumber) {
      var sequence = lift.nextSaveSequence + 1;
      var coverage;
      var payload;
      lift.nextSaveSequence = sequence;
      if (field === "earlierSetReps") {
        coverage = Object.create(null);
        coverage["earlierSetReps." + setNumber]
          = lift.fieldRevisions.earlierSetReps[setNumber];
        payload = {
          expectedWeek: expectedWeek,
          slotId: lift.slotId,
          saveSequence: sequence,
          focusedSlotId: focus.slotId,
          focusSequence: focus.sequence,
          setNumber: setNumber,
          reps: lift.draft.earlierSetReps[setNumber],
        };
      } else {
        coverage = {
          addedWeight: lift.fieldRevisions.addedWeight,
          driverReps: lift.fieldRevisions.driverReps,
        };
        payload = {
          expectedWeek: expectedWeek,
          slotId: lift.slotId,
          saveSequence: sequence,
          focusedSlotId: focus.slotId,
          focusSequence: focus.sequence,
          setNumber: lift.driverSetNumber,
          actualAddedWeight: lift.draft.addedWeight,
          reps: lift.draft.driverReps,
        };
      }
      return {
        sequence: sequence,
        coverage: Object.freeze(coverage),
        payload: Object.freeze(payload),
      };
    }

    function startNextSave(lift) {
      if (lift.inFlight || !lift.queue.length) return null;
      lift.inFlight = lift.queue.shift();
      return {
        type: "request",
        role: "save",
        payload: lift.inFlight.payload,
      };
    }

    function inspectorRequest(lift, intent) {
      var payload = {
        expectedWeek: expectedWeek,
        slotId: lift.slotId,
        focusSequence: focus.sequence,
      };
      if (intent === "skip") {
        payload.intent = "skip";
      } else {
        payload.actualAddedWeight = lift.draft.addedWeight;
        payload.driverReps = lift.draft.driverReps;
      }
      return {
        type: "request",
        role: "inspector",
        payload: Object.freeze(payload),
      };
    }

    function focusEvent(lift) {
      if (lift.intentRequest) return [workspaceRender()];
      focusLift(lift);
      return [workspaceRender(), inspectorRequest(lift, lift.settlementIntent)];
    }

    function settlementIntentEvent(lift, intent) {
      if (pendingCount(lift) > 0 || lift.serverSnapshot.hasDriverFact) {
        return [workspaceRender()];
      }
      focusLift(lift);
      lift.intentError = null;
      lift.intentRequest = Object.freeze({
        expectedWeek: expectedWeek, slotId: lift.slotId,
        focusSequence: focus.sequence, intent: intent,
      });
      return [
        workspaceRender(),
        {type: "request", role: "settlement", payload: lift.intentRequest},
      ];
    }

    function settlementResult(lift, event) {
      if (!lift.intentRequest
          || Number(event.focusSequence) !== lift.intentRequest.focusSequence) return [];
      if (event.staleWeek) return stopForStaleWeek();
      if (event.success) {
        lift.settlementIntent = lift.intentRequest.intent;
      } else {
        lift.intentError = event.error || "请求失败";
      }
      lift.intentRequest = null;
      var effects = inspectorResult(lift, event);
      return effects.length ? effects : [workspaceRender()];
    }

    function nextUnresolvedEvent() {
      var lift = nextActionableLift();
      if (lift) {
        focusLift(lift);
        return [workspaceRender(), inspectorRequest(lift)];
      }
      return [workspaceRender()];
    }

    function change(lift, event) {
      if (lift.intentRequest || lift.settlementIntent === "skip") return [];
      lift.intentError = null;
      var setNumber;
      if (event.field === "addedWeight" || event.field === "driverReps") {
        lift.draft[event.field] = event.value;
        lift.fieldRevisions[event.field] += 1;
      } else if (event.field === "earlierSetReps") {
        setNumber = String(event.setNumber);
        lift.draft.earlierSetReps[setNumber] = event.value;
        lift.fieldRevisions.earlierSetReps[setNumber]
          = (lift.fieldRevisions.earlierSetReps[setNumber] || 0) + 1;
      } else {
        throw new TypeError("Unknown Week Workspace change field: " + event.field);
      }
      focusLift(lift);
      lift.queue.push(frozenSaveAttempt(lift, event.field, setNumber));
      var request = startNextSave(lift);
      var effects = [workspaceRender()];
      if (request) effects.push(request);
      return effects;
    }

    function applySaveSuccess(lift, attempt, event) {
      var accepted = event.coverage || Object.keys(attempt.coverage);
      accepted.forEach(function (path) {
        if (Object.prototype.hasOwnProperty.call(attempt.coverage, path)) {
          var prior = lift.acceptedRevisions[path];
          var revision = attempt.coverage[path];
          lift.acceptedRevisions[path] = prior === undefined
            ? revision
            : Math.max(prior, revision);
        }
      });
      if (event.serverSnapshot) {
        Object.keys(event.serverSnapshot).forEach(function (name) {
          if (name !== "coverage") {
            lift.serverSnapshot[name] = copyValue(event.serverSnapshot[name]);
          }
        });
      }
      if (accepted.indexOf("driverReps") !== -1) {
        if (!event.serverSnapshot
            || !Object.prototype.hasOwnProperty.call(
              event.serverSnapshot, "driverReps"
            )) {
          lift.serverSnapshot.driverReps = attempt.payload.reps;
        }
        if (!event.serverSnapshot
            || !Object.prototype.hasOwnProperty.call(
              event.serverSnapshot, "hasDriverFact"
            )) {
          lift.serverSnapshot.hasDriverFact = true;
        }
      }
    }

    function stopForStaleWeek() {
      requestsStopped = true;
      return [{
        type: "render",
        role: "reload",
        expectedWeek: expectedWeek,
        reason: "stale-week",
      }];
    }

    function saveResult(lift, event) {
      if (!lift.inFlight
          || lift.inFlight.sequence !== Number(event.saveSequence)) return [];
      if (event.staleWeek) return stopForStaleWeek();
      var attempt = lift.inFlight;
      lift.inFlight = null;
      if (event.success) {
        applySaveSuccess(lift, attempt, event);
        lift.lastTerminal = {sequence: attempt.sequence, status: "succeeded"};
      } else {
        lift.lastTerminal = {
          sequence: attempt.sequence,
          status: "failed",
          error: event.error || "请求失败",
          affectsSettlement: attemptAffectsSettlement(attempt),
        };
      }
      var request = startNextSave(lift);
      var effects = [workspaceRender()];
      if (Object.prototype.hasOwnProperty.call(event, "persistentFragment")) {
        effects.push({
          type: "render",
          role: "persistent",
          slotId: lift.slotId,
          fragment: event.persistentFragment,
        });
      }
      if (Object.prototype.hasOwnProperty.call(event, "inspectorFragment")
          && slotKey(event.focusedSlotId)
            === slotKey(attempt.payload.focusedSlotId)
          && Number(event.focusSequence) === attempt.payload.focusSequence
          && slotKey(event.focusedSlotId) === slotKey(focus.slotId)
          && Number(event.focusSequence) === focus.sequence) {
        effects.push({
          type: "render",
          role: "inspector",
          slotId: focus.slotId,
          focusSequence: focus.sequence,
          fragment: event.inspectorFragment,
        });
      }
      if (request) effects.push(request);
      return effects;
    }

    function inspectorResult(lift, event) {
      if (event.staleWeek) return stopForStaleWeek();
      if (slotKey(lift.slotId) !== slotKey(focus.slotId)
          || Number(event.focusSequence) !== focus.sequence) return [];
      var effect = {
        type: "render",
        role: "inspector",
        slotId: lift.slotId,
        focusSequence: focus.sequence,
      };
      if (Object.prototype.hasOwnProperty.call(event, "inspectorFragment")) {
        effect.fragment = event.inspectorFragment;
      }
      if (!event.success) effect.error = event.error || "请求失败";
      return [workspaceRender(), effect];
    }

    return function handle(event) {
      if (event.expectedWeek !== expectedWeek) return [];
      if (requestsStopped) return [];
      if (event.type === "bootstrap") return [workspaceRender()];
      if (event.type === "nextUnresolved") return nextUnresolvedEvent();
      var lift = liftsBySlotId[slotKey(event.slotId)];
      if (event.type === "change") return lift ? change(lift, event) : [];
      if (event.type === "focus") return lift ? focusEvent(lift) : [];
      if (event.type === "skip") {
        return lift ? settlementIntentEvent(lift, "skip") : [];
      }
      if (event.type === "resume") {
        return lift ? settlementIntentEvent(lift, "record") : [];
      }
      if (event.type === "saveResult") {
        return lift ? saveResult(lift, event) : [];
      }
      if (event.type === "settlementResult") {
        return lift ? settlementResult(lift, event) : [];
      }
      if (event.type === "inspectorResult") {
        return lift ? inspectorResult(lift, event) : [];
      }
      throw new TypeError("Unknown Week Workspace event: " + event.type);
    };
  }

  return createWeekWorkspace;
}));
