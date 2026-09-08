# FabTwin v1 Case Studies — locked designs

**Status:** the three case designs below are locked at P0 (2026-09-08) per
Overview §4.4. This is a **design lock**, not a `configs/` YAML lock —
`configs/` stays empty until Gate T1, when the simulator's actual parameter
names exist to write real config files against (see `configs/README.md`).
Writing YAML now, before the simulator's config schema is designed, would
just get rewritten and risks silently drifting from what T1 actually builds.

What *is* locked now, and must not change without an ADR: which fault/
comparison each case exercises, what gets compared, and the seed policy.

---

## Case 1 — Chamber drift

**Fault:** `linear_drift` (docs/data-dictionary.md §6) on one chamber within
a single tool; the sibling chamber stays fault-free as an implicit control.

**Compares:** detection delay and false-alarm count across three univariate
methods on the same drifting metric — I-MR, EWMA, CUSUM (Overview §4.2, §4.4).

**Question it answers:** among methods that are all valid for a single
time-series metric, how much does the choice of method change how fast a
slow drift gets caught, and at what false-alarm cost?

## Case 2 — Tool/chamber comparison

**Fault:** none. Two chambers configured with **similar means but different
variance** (a `variance_inflation`-shaped difference baked into the baseline
config, not injected as a fault event — this is a steady-state comparison,
not a fault-detection scenario).

**Compares:** Cp/Cpk, Pp/Ppk, wafer yield, and confidence intervals between
the two chambers.

**Question it answers:** the Overview's own framing (§4.4) — "平均值正常"不等
于过程健康. This case exists specifically to produce a pair of chambers where
naive mean-comparison says "both fine" while capability/yield says otherwise.

## Case 3 — Degradation → maintenance → recovery

**Fault:** `monotonic_equipment_degradation` (duration_s = null, i.e. ongoing)
on one tool/chamber, terminated by a `recovery_action` representing a
maintenance event.

**Compares:** alarm lead time (time from first alarm to the point the metric
would have breached spec, had no maintenance occurred), and
capability/yield/DPPM before vs. after the maintenance event.

**Question it answers:** does the monitoring system give enough lead time to
act before a slow degradation becomes a yield problem, and does the
before/after comparison actually show recovery (not just "alarm fired").

---

## Seed policy (all three cases, per Overview §4.4)

- One **canonical seed** per case, used for the UI demo and any figure meant
  to show "what a run looks like."
- At least **30 seeds** per case for the summary statistics (median, IQR /
  95% interval) that any resume bullet or report headline number is allowed
  to cite. A single-seed number is a demo artifact, not a claimable result.
- Results may come out unfavorable (e.g. a method fails to detect a fault
  within a reasonable delay) — that is a valid, reportable outcome, not a
  bug to hide. Overview §4.4: "结果可以好也可以不好，不预设'必须提升 20%'。"

## What's still open (resolved when `configs/` is authored at T1)

- Exact drift rate / variance-inflation factor / degradation rate magnitudes
  for each case — these are tuning choices made once the simulator exists
  and can be inspected, not decided blind now.
- Whether case 2's variance difference is expressed as two different
  `variance_inflation`-style baseline parameters or as a distinct config
  field outside the fault-event vocabulary (since it's steady-state, not an
  injected event) — an implementation decision for T1, not a schema change.
