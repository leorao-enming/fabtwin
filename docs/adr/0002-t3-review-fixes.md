# ADR 0002: T3 review fixes - fault metric scope, detection window, DPPM definition

- **Status:** accepted
- **Date:** 2026-11-21
- **Gate:** T3

## Context

A review of the T3 deliverables against Overview §4.3 on 2026-11-05 (at `775ce5e`, all
existing checks green) found six problems with independent probes. Three of them need the
data dictionary itself to change, which §1-§8 say requires an ADR:

1. A fault on `etch_rate` or `wiwnu` was accepted by the schema and the config model but
   changed no data at all: both metrics are computed from `etch_depth` (§3), so there is no
   independently simulated value for the fault to act on.
2. Detection scoring credited any alarm at or after onset, including alarms long after a
   fault had ended; it scored faults whose onset fell inside the Phase I window (limits
   fitted on faulty data); and it scored a fault against a chart of a different chamber or
   metric without complaint.
3. §8 asks for a numeric "defect definition threshold" for DPPM. The simulator generates
   `defect_count` directly; there is no defect size or signal to threshold.

The other three were the code not following the existing contract: degradation was per
hour, not per lot processed (§6); `variance_inflation` scaled site measurement noise
rather than the process-level sigma (§6); and a `defect_count` fault changed thousands of
unrelated values because all chambers shared one random stream whose consumption depended
on the Poisson sampler (§4.6 requires a fault to affect only its declared scope).

## Decision

1. **§6 fault scope:** `affected_scope.metric` is one of `etch_depth`, `cd_bias`,
   `defect_count`. A fault on `etch_depth` reaches `etch_rate` and `wiwnu` through the §3
   formulas. Faults declared on derived metrics are rejected at validation.
2. **§7 detection window:** an alarm is a detection only while the fault is active
   (`FaultEvent.active_at`: after onset, before `duration_s` ends and before any
   `recovery_action`). Alarms after that are a new field, `post_fault_alarms` (int >= 0).
   Scoring raises instead of returning a score when the fault is active anywhere in Phase I,
   when it is never active in Phase II, or when its (tool, chamber, metric) does not match
   the chart's; an `etch_depth` fault may be scored on `etch_rate`/`wiwnu` charts. A chart
   of another chamber can be scored only as an explicit sibling control
   (`score_detection(..., sibling_control=True)`).
3. **§8 DPPM:** the defect definition is recorded as text (`defect_definition`), together
   with the opportunity count; no numeric threshold.

Contract-conformance fixes recorded here for completeness (no dictionary change):
degradation `magnitude` is drift per **lot** processed on the affected chamber in v1, the
first affected lot has zero offset, and the lot count is never defaulted; `variance_inflation`
scales the lot and wafer sigma, not site noise; each chamber has its own random stream
(`SeedSequence([seed, crc32(tool_id), crc32(chamber_id)])`) and every draw consumes a fixed
number of variates (`defect_count` uses one uniform and the inverse CDF). The last change
alters every seed's output, which is why it lands before any case study is frozen.

## Alternatives considered

- **Simulate `etch_rate`/`wiwnu` faults as post-hoc offsets on the derived values** - breaks
  the §3 identity `etch_rate = etch_depth / etch_time_s * 60`, so the observation table would
  contradict its own definitions.
- **Keep crediting post-fault alarms (any alarm after onset)** - this is what made a fault
  that ended at hour 3 "detected" at hour 20 with an 18 h delay; it rewards charts that alarm
  for unrelated reasons.
- **Clip the detection window instead of raising for Phase I overlap** - would still report
  numbers computed from contaminated limits.
- **Keep one shared random stream and accept cross-scope changes** - makes same-seed
  "with vs without fault" comparisons (needed by all three case studies) meaningless.

## Consequences

- EWMA and CUSUM carry memory, so an alarm just after a short fault ends is no longer
  credited. This is deliberately strict; it is the first thing to revisit if case 3 shows
  it misrepresents those charts.
- Every seed produces different numbers than before. Tests that asserted "a healthy
  chamber never alarms" for one seed failed after the change; measured over 200 seeds, a
  3-sigma chart with a 10-lot Phase I shows at least one false alarm in 20 lots 27 % (I-MR)
  / 21 % (EWMA) of the time. Those tests now compare alarm counts.
- Callers must say which chamber a chart is of (`SPCRunResult` carries `tool_id`,
  `chamber_id`, `metrics`), and sibling comparisons must be declared.

## Rollback trigger

If case 3 (degradation -> maintenance -> recovery) cannot credit a detection that a process
engineer would plainly call timely because the alarm lands just after recovery, revisit the
detection window in a new ADR (for example, a declared grace period per method) rather than
loosening it silently.
