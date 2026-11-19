/* One lifecycle decision used by browser, estimator and static API generator. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.LLMAvailability = factory();
})(typeof globalThis === "undefined" ? this : globalThis, function () {
  "use strict";
  var PRECISE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
  function instant(value) {
    if (typeof value !== "string" || !PRECISE.test(value) || !Number.isFinite(Date.parse(value))) return null;
    if (new Date(value.slice(0, 10)).toISOString().slice(0, 10) !== value.slice(0, 10)) return null;
    return Date.parse(value);
  }
  function availability(model, at) {
    var time = instant(at), life = model.lifecycle;
    if (time === null) throw new Error("Availability requires an ISO instant with timezone");
    if (!life) return { status: "active", estimable: true, reason: null };
    var end = instant(life.retired_at);
    // A confirmed retired entity is not an uncertain future date. Observation
    // establishes what was already true then; it does NOT invent retirement T.
    if (life.status === "retired" && !life.conflict &&
        (end === null || life.precision !== "instant" || !life.timezone)) {
      var observed = instant(life.observed_at);
      return { status: observed !== null && time < observed ? "history_unknown" : "retired",
        estimable: false, reason: life.note };
    }
    // Conflicting official statements or date-only announcements are not automatic retirement.
    if (life.status === "pending_confirmation" || life.conflict || (life.retired_at && (life.precision !== "instant" || !life.timezone)) || (life.retired_at && end === null) || (!life.retired_at && (life.retirement_date || life.status === "pending_confirmation")))
      return { status: "pending_confirmation", estimable: true, reason: life.note };
    if (end !== null && time >= end)
      return { status: "retired", estimable: false, reason: life.note };
    return { status: end !== null ? "scheduled" : "active", estimable: true, reason: life.note };
  }
  return { availability: availability, instant: instant };
});
