"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createWeekWorkspace,
} = require("../webapp/static/week_workspace.js");


function workspaceView(effects) {
  return effects.find(function (effect) {
    return effect.type === "render" && effect.role === "workspace";
  }).view;
}


function requestEffect(effects, role) {
  return effects.find(function (effect) {
    return effect.type === "request" && effect.role === role;
  });
}


function liftView(effects, slotId) {
  return workspaceView(effects).lifts.find(function (lift) {
    return lift.slotId === slotId;
  });
}


function renderEffect(effects, role) {
  return effects.find(function (effect) {
    return effect.type === "render" && effect.role === role;
  });
}


test("snapshot projects blank, persisted zero, and ready lifts", function () {
  const handle = createWeekWorkspace({
    expectedWeek: 7,
    focusedSlotId: 11,
    lifts: [
      {
        slotId: 11,
        driverSetNumber: 3,
        draft: {addedWeight: 30, driverReps: "", earlierSetReps: {}},
        serverSnapshot: {
          settlementReady: false,
          hasDriverFact: false,
          coverage: [],
        },
      },
      {
        slotId: 12,
        driverSetNumber: 3,
        draft: {addedWeight: 40, driverReps: 0, earlierSetReps: {}},
        serverSnapshot: {
          settlementReady: true,
          hasDriverFact: true,
          driverReps: 0,
          coverage: ["addedWeight", "driverReps"],
        },
      },
      {
        slotId: 13,
        driverSetNumber: 5,
        draft: {addedWeight: 75, driverReps: 9, earlierSetReps: {}},
        serverSnapshot: {
          settlementReady: true,
          hasDriverFact: true,
          driverReps: 9,
          coverage: ["addedWeight", "driverReps"],
        },
      },
    ],
  });

  const view = workspaceView(handle({type: "bootstrap", expectedWeek: 7}));

  assert.deepEqual(
    view.lifts.map(function (lift) {
      return [lift.slotId, lift.state, lift.failedZero];
    }),
    [
      [11, "unresolved", false],
      [12, "logged", true],
      [13, "logged", false],
    ]
  );
  assert.equal(view.handled, 2);
  assert.equal(view.pending, 1);
  assert.equal(view.nextUnresolvedSlotId, 11);
  assert.equal(view.reviewEligible, false);
});


test("same-lift saves are FIFO with frozen payloads and attempt-owned errors", function () {
  const handle = createWeekWorkspace({
    expectedWeek: 7,
    focusedSlotId: 11,
    lifts: [{
      slotId: 11,
      driverSetNumber: 3,
      draft: {addedWeight: 30, driverReps: 8, earlierSetReps: {}},
      serverSnapshot: {
        settlementReady: false,
        hasDriverFact: false,
        coverage: [],
      },
    }],
  });

  const first = handle({
    type: "change",
    expectedWeek: 7,
    slotId: 11,
    field: "addedWeight",
    value: 32.5,
  });
  const firstRequest = requestEffect(first, "save");
  assert.deepEqual(firstRequest.payload, {
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 1,
    focusedSlotId: 11,
    focusSequence: 1,
    setNumber: 3,
    actualAddedWeight: 32.5,
    reps: 8,
  });

  const second = handle({
    type: "change",
    expectedWeek: 7,
    slotId: 11,
    field: "driverReps",
    value: 9,
  });
  assert.equal(requestEffect(second, "save"), undefined);
  assert.equal(liftView(second, 11).saving, true);
  assert.equal(liftView(second, 11).error, null);
  assert.equal(firstRequest.payload.reps, 8);

  const afterFirstFailure = handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 1,
    success: false,
    error: "first failed",
  });
  const secondRequest = requestEffect(afterFirstFailure, "save");
  assert.deepEqual(secondRequest.payload, {
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 2,
    focusedSlotId: 11,
    focusSequence: 2,
    setNumber: 3,
    actualAddedWeight: 32.5,
    reps: 9,
  });
  assert.equal(liftView(afterFirstFailure, 11).error, null);

  const afterSuccess = handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 2,
    success: true,
    serverSnapshot: {
      settlementReady: true,
      hasDriverFact: true,
      driverReps: 9,
    },
  });
  assert.equal(liftView(afterSuccess, 11).state, "logged");
  assert.equal(liftView(afterSuccess, 11).error, null);

  const third = handle({
    type: "change",
    expectedWeek: 7,
    slotId: 11,
    field: "driverReps",
    value: 10,
  });
  assert.equal(requestEffect(third, "save").payload.saveSequence, 3);

  const afterThirdFailure = handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 3,
    success: false,
    error: "third failed",
  });
  assert.equal(liftView(afterThirdFailure, 11).state, "unresolved");
  assert.equal(liftView(afterThirdFailure, 11).error, "third failed");

  const skippedAfterFailure = handle({
    type: "skip",
    expectedWeek: 7,
    slotId: 11,
  });
  assert.equal(liftView(skippedAfterFailure, 11).state, "logged");
  assert.equal(liftView(skippedAfterFailure, 11).error, null);
});


test("cross-lift saves run in parallel while obsolete inspectors are discarded", function () {
  const handle = createWeekWorkspace({
    expectedWeek: 7,
    focusedSlotId: 11,
    lifts: [
      {
        slotId: 11,
        driverSetNumber: 3,
        draft: {addedWeight: 30, driverReps: "", earlierSetReps: {}},
        serverSnapshot: {settlementReady: false, coverage: []},
      },
      {
        slotId: 12,
        driverSetNumber: 3,
        draft: {addedWeight: 40, driverReps: "", earlierSetReps: {}},
        serverSnapshot: {settlementReady: false, coverage: []},
      },
    ],
  });

  const saveEleven = requestEffect(handle({
    type: "change",
    expectedWeek: 7,
    slotId: 11,
    field: "driverReps",
    value: 8,
  }), "save");
  const saveTwelve = requestEffect(handle({
    type: "change",
    expectedWeek: 7,
    slotId: 12,
    field: "driverReps",
    value: 9,
  }), "save");

  assert.equal(saveEleven.payload.saveSequence, 1);
  assert.equal(saveTwelve.payload.saveSequence, 1);
  assert.equal(saveEleven.payload.focusSequence, 1);
  assert.equal(saveTwelve.payload.focusSequence, 2);

  const focusRequest = requestEffect(handle({
    type: "focus",
    expectedWeek: 7,
    slotId: 12,
  }), "inspector");
  assert.deepEqual(focusRequest.payload, {
    expectedWeek: 7,
    slotId: 12,
    focusSequence: 3,
    actualAddedWeight: 40,
    driverReps: 9,
  });

  const lateEleven = handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 1,
    focusedSlotId: 12,
    focusSequence: 3,
    success: true,
    serverSnapshot: {
      settlementReady: true,
      hasDriverFact: true,
      driverReps: 8,
    },
    persistentFragment: "persistent eleven",
    inspectorFragment: "relabelled inspector eleven",
  });
  assert.equal(renderEffect(lateEleven, "persistent").fragment,
               "persistent eleven");
  assert.equal(renderEffect(lateEleven, "inspector"), undefined);
  assert.equal(workspaceView(lateEleven).focusedSlotId, 12);
  assert.equal(liftView(lateEleven, 11).state, "logged");

  const lateTwelve = handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 12,
    saveSequence: 1,
    focusedSlotId: 12,
    focusSequence: 2,
    success: true,
    serverSnapshot: {
      settlementReady: true,
      hasDriverFact: true,
      driverReps: 9,
    },
    persistentFragment: "persistent twelve",
    inspectorFragment: "obsolete inspector twelve",
  });
  assert.equal(renderEffect(lateTwelve, "persistent").fragment,
               "persistent twelve");
  assert.equal(renderEffect(lateTwelve, "inspector"), undefined);

  const failedInspector = handle({
    type: "inspectorResult",
    expectedWeek: 7,
    slotId: 12,
    focusSequence: 3,
    success: false,
    error: "preview failed",
  });
  assert.equal(renderEffect(failedInspector, "inspector").error,
               "preview failed");
  assert.equal(renderEffect(failedInspector, "inspector").fragment, undefined);
  assert.equal(workspaceView(failedInspector).pending, 0);

  const currentInspector = handle({
    type: "inspectorResult",
    expectedWeek: 7,
    slotId: 12,
    focusSequence: 3,
    success: true,
    inspectorFragment: "current inspector twelve",
  });
  assert.equal(renderEffect(currentInspector, "inspector").fragment,
               "current inspector twelve");
  assert.equal(workspaceView(currentInspector).focusedSlotId, 12);
});


test("pending skip and resume keep saves intact while next and review stay derived", function () {
  const handle = createWeekWorkspace({
    expectedWeek: 7,
    focusedSlotId: 12,
    lifts: [
      {
        slotId: 11,
        driverSetNumber: 3,
        draft: {addedWeight: 30, driverReps: "", earlierSetReps: {}},
        serverSnapshot: {settlementReady: false, coverage: []},
      },
      {
        slotId: 12,
        driverSetNumber: 3,
        draft: {addedWeight: 40, driverReps: 8, earlierSetReps: {}},
        serverSnapshot: {
          settlementReady: true,
          hasDriverFact: true,
          driverReps: 8,
          coverage: ["addedWeight", "driverReps"],
        },
      },
      {
        slotId: 13,
        driverSetNumber: 3,
        draft: {addedWeight: 50, driverReps: "", earlierSetReps: {}},
        serverSnapshot: {settlementReady: false, coverage: []},
      },
    ],
  });

  handle({
    type: "change",
    expectedWeek: 7,
    slotId: 11,
    field: "driverReps",
    value: 9,
  });
  const skippedPending = handle({
    type: "skip",
    expectedWeek: 7,
    slotId: 11,
  });
  assert.deepEqual(requestEffect(skippedPending, "inspector").payload, {
    expectedWeek: 7,
    slotId: 11,
    focusSequence: 2,
    intent: "skip",
  });
  assert.equal(liftView(skippedPending, 11).state, "unresolved");
  assert.equal(liftView(skippedPending, 11).saving, true);

  const resumedPending = handle({
    type: "resume",
    expectedWeek: 7,
    slotId: 11,
  });
  assert.deepEqual(requestEffect(resumedPending, "inspector").payload, {
    expectedWeek: 7,
    slotId: 11,
    focusSequence: 3,
    actualAddedWeight: 30,
    driverReps: 9,
  });
  assert.equal(liftView(resumedPending, 11).state, "unresolved");

  const moved = handle({type: "nextUnresolved", expectedWeek: 7});
  assert.equal(workspaceView(moved).focusedSlotId, 13);
  assert.equal(requestEffect(moved, "inspector").payload.slotId, 13);

  const failed = handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 1,
    success: false,
    error: "save failed",
  });
  assert.equal(liftView(failed, 11).state, "unresolved");
  assert.equal(liftView(failed, 11).error, "save failed");

  const skippedEleven = handle({
    type: "skip",
    expectedWeek: 7,
    slotId: 11,
  });
  assert.equal(liftView(skippedEleven, 11).state, "skipped");
  assert.equal(liftView(skippedEleven, 11).error, null);
  assert.equal(workspaceView(skippedEleven).handled, 2);
  assert.equal(workspaceView(skippedEleven).pending, 1);

  const skippedThirteen = handle({
    type: "skip",
    expectedWeek: 7,
    slotId: 13,
  });
  assert.equal(workspaceView(skippedThirteen).handled, 3);
  assert.equal(workspaceView(skippedThirteen).pending, 0);
  assert.equal(workspaceView(skippedThirteen).nextUnresolvedSlotId, null);
  assert.equal(workspaceView(skippedThirteen).reviewEligible, true);

  const resumedEleven = handle({
    type: "resume",
    expectedWeek: 7,
    slotId: 11,
  });
  assert.equal(liftView(resumedEleven, 11).state, "unresolved");
  assert.equal(liftView(resumedEleven, 11).error, "save failed");
  assert.equal(workspaceView(resumedEleven).reviewEligible, false);
});


test("earlier-set and blank changes each freeze exactly one set request", function () {
  const handle = createWeekWorkspace({
    expectedWeek: 7,
    focusedSlotId: 11,
    lifts: [{
      slotId: 11,
      driverSetNumber: 3,
      draft: {
        addedWeight: 30,
        driverReps: 8,
        earlierSetReps: {1: ""},
      },
      serverSnapshot: {
        settlementReady: true,
        hasDriverFact: true,
        driverReps: 8,
        coverage: ["addedWeight", "driverReps"],
      },
    }],
  });

  const earlier = handle({
    type: "change",
    expectedWeek: 7,
    slotId: 11,
    field: "earlierSetReps",
    setNumber: 1,
    value: 6,
  });
  assert.deepEqual(requestEffect(earlier, "save").payload, {
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 1,
    focusedSlotId: 11,
    focusSequence: 1,
    setNumber: "1",
    reps: 6,
  });
  assert.equal(requestEffect(earlier, "inspector"), undefined);

  const saved = handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 1,
    success: true,
    serverSnapshot: {settlementReady: true},
  });
  assert.equal(liftView(saved, 11).state, "logged");

  const blank = handle({
    type: "change",
    expectedWeek: 7,
    slotId: 11,
    field: "driverReps",
    value: "",
  });
  assert.equal(requestEffect(blank, "save").payload.reps, "");
  assert.equal(requestEffect(blank, "inspector"), undefined);
});


test("wrong identities are ignored and authoritative stale week stops requests", function () {
  const handle = createWeekWorkspace({
    expectedWeek: 7,
    focusedSlotId: 11,
    lifts: [{
      slotId: 11,
      driverSetNumber: 3,
      draft: {addedWeight: 30, driverReps: "", earlierSetReps: {}},
      serverSnapshot: {settlementReady: false, coverage: []},
    }],
  });

  assert.deepEqual(handle({
    type: "change",
    expectedWeek: 6,
    slotId: 11,
    field: "driverReps",
    value: 8,
  }), []);
  assert.deepEqual(handle({
    type: "inspectorResult",
    expectedWeek: 7,
    slotId: 999,
    focusSequence: 0,
    success: true,
    inspectorFragment: "wrong slot",
  }), []);

  handle({
    type: "change",
    expectedWeek: 7,
    slotId: 11,
    field: "driverReps",
    value: 8,
  });
  assert.deepEqual(handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 99,
    success: true,
    persistentFragment: "wrong sequence",
  }), []);
  assert.deepEqual(handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 99,
    staleWeek: true,
  }), []);

  const stale = handle({
    type: "saveResult",
    expectedWeek: 7,
    slotId: 11,
    saveSequence: 1,
    staleWeek: true,
  });
  assert.deepEqual(stale, [{
    type: "render",
    role: "reload",
    expectedWeek: 7,
    reason: "stale-week",
  }]);

  assert.deepEqual(handle({
    type: "change",
    expectedWeek: 7,
    slotId: 11,
    field: "driverReps",
    value: 9,
  }), []);
});


test("authoritative inspector stale week stops after focus moves", function () {
  const handle = createWeekWorkspace({
    expectedWeek: 7,
    focusedSlotId: 11,
    lifts: [
      {
        slotId: 11,
        driverSetNumber: 3,
        draft: {addedWeight: 30, driverReps: "", earlierSetReps: {}},
        serverSnapshot: {settlementReady: false, coverage: []},
      },
      {
        slotId: 12,
        driverSetNumber: 3,
        draft: {addedWeight: 40, driverReps: "", earlierSetReps: {}},
        serverSnapshot: {settlementReady: false, coverage: []},
      },
    ],
  });

  handle({type: "focus", expectedWeek: 7, slotId: 12});
  const stale = handle({
    type: "inspectorResult",
    expectedWeek: 7,
    slotId: 11,
    focusSequence: 0,
    success: false,
    staleWeek: true,
  });

  assert.deepEqual(stale, [{
    type: "render",
    role: "reload",
    expectedWeek: 7,
    reason: "stale-week",
  }]);
  assert.deepEqual(handle({
    type: "change",
    expectedWeek: 7,
    slotId: 12,
    field: "driverReps",
    value: 8,
  }), []);
});
