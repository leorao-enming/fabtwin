# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this project uses `vX.Y.Z` tags
only at real release Gates (T5 = v1.0.0), not for intermediate work.

## [Unreleased]

### Added

- P0 repo skeleton: directory layout, Makefile command surface, CI (ruff + mypy +
  pytest + validation smoke), ADR template, issue templates, evidence schema.
- `docs/data-dictionary.md`: locked v1 process hierarchy (tool/chamber/lot/wafer/
  site), the five output metrics with units, and the observation and fault-event
  record schemas.
- `docs/case-studies.md`: locked designs for the three Gate T4 case studies
  (chamber drift, tool/chamber comparison, degradation → maintenance → recovery)
  and the multi-seed reporting policy.
- `docs/schemas/observation.schema.json`, `docs/schemas/fault-event.schema.json`.
- `evidence/case-manifest.schema.json` plus a hand-written fixture and pytest
  checks, proving the case-run evidence pipeline ahead of Gate T4.
- Published to GitHub (`github.com/leorao-enming/fabtwin`, public) with all 7
  gate milestones (P0, T1–T5, P1).

### Fixed

- P0 `scripts/validate.py`: `datetime.UTC` alias, line-length lint findings.
- CI push trigger watched `branches: [main]`; the actual default branch is
  `master`, so no CI run had ever fired since the repo was created. Corrected
  to `branches: [master]` — first real GitHub Actions run passed green.

## [T1 in progress] — 2026-09-09

### Added

- `src/fabtwin/config.py`: pydantic models for the full simulator input
  contract (`RecipeConfig`, `ToolChamberConfig`, `FaultEvent`,
  `HierarchyConfig`, `RandomEffectConfig`, `SimulationConfig`), matching
  `docs/data-dictionary.md` and `docs/schemas/fault-event.schema.json`
  exactly, with cross-validation that every fault targets a real
  tool/chamber in the run.
- `src/fabtwin/effects.py`: the fixed recipe effect (documented synthetic
  calibration) plus the tool/chamber, lot, and wafer random-effect draws and
  measurement noise, all through one caller-supplied RNG.
- `src/fabtwin/faults.py`: the five fault types as composable, scope-matched
  contributions — step_mean_shift, linear_drift, and
  monotonic_equipment_degradation as additive process-value shifts (the
  latter stopping at its `recovery_action`), variance_inflation as a
  measurement-noise sigma multiplier, and sensor_bias kept strictly
  measurement-stage-only.
- `src/fabtwin/metrics.py`: `etch_rate`/`wiwnu` derived from `etch_depth`
  per the locked formulas; `defect_count` as a v1 Poisson/negative-binomial
  generator per the data dictionary's explicit "simple generator is fine
  for T1" call.
- `src/fabtwin/simulator.py`: `simulate(config) -> SimulationResult`,
  assembling the above into the exact long-format observation table from
  the data dictionary, with the hidden-truth decomposition kept in a
  separate field observations never leak into.
- 42 new unit tests across the four modules, including an end-to-end
  chamber-drift scenario proving a fault on one chamber does not leak into
  its sibling. Full repo: ruff clean, mypy clean, 42/42 tests pass, all
  three commits ran green on real GitHub Actions.

### Not yet done (T1 remaining)

- Fault-ground-truth-vs-detection scoring (Gate T3), the three frozen case
  configs and Streamlit dashboard (Gate T4) are all still not started. This
  simulator has not yet been run end-to-end through `make cases` or
  connected to `app/main.py`.

## [T2 in progress] — 2026-09-12

### Added

- `src/fabtwin/spc/phase.py`: the Phase I/II split as an immutable
  `FrozenLimits` dataclass — a chart's Phase II "apply" function can never
  re-estimate limits from the data it is scoring, structurally preventing
  the "recompute limits on fault-contaminated data" mistake the Overview
  explicitly forbids.
- `src/fabtwin/spc/imr.py`: Individuals (X) and Moving Range chart.
- `src/fabtwin/spc/ewma.py`: EWMA chart, with the NIST EWMA_0..EWMA_n
  indexing convention implemented exactly (not guessed).
- `src/fabtwin/spc/capability.py`: Cp/Cpk (within/common-cause sigma) and
  Pp/Ppk (overall sigma) sharing one formula core but kept as distinct
  sigma sources, plus a small-sample-size warning.
- Every formula checked against a real NIST Engineering Statistics Handbook
  worked example (sections 6.3.2.2, 6.3.2.4, 6.1.6), not just internal
  self-consistency — including reproducing NIST's own stated conclusions
  ("process is in control", "Cpk<1.0, not a good process"). See the EWMA
  test file's docstring for a provenance note: an earlier page fetch gave
  an ambiguous EWMA series, and the fixture used here was re-verified by
  re-fetching the raw table and hand-recomputing the recursion before being
  hardcoded.
- 24 new tests (66/66 repo-wide), ruff/mypy clean, GitHub Actions green.

### Not yet done (T2 remaining)

- Xbar-R/Xbar-S subgroup charts, CUSUM, and the Western Electric/Nelson
  rule engine are not built yet — do not treat Gate T2 as complete.

## [T1<->T2 integration] — 2026-09-12

### Added

- `src/fabtwin/analysis.py`: the first place the T1 simulator's observation
  table and the T2 `spc/` package actually meet. `extract_lot_series()`
  turns the long-format observation table into a per-lot time series;
  `split_phase_i_ii()` is the prefix/suffix Phase I/II window;
  `run_imr`/`run_ewma`/`run_capability` chain a Phase I fit + Phase II
  scoring, always from the Phase I window only.
- Integration tests call `simulate()` for real (not hand-built lists): a
  case-1-shaped chamber-drift scenario where both I-MR and EWMA flag the
  drifting chamber and do not false-alarm on its untouched sibling, and a
  case-2-shaped scenario (steady `variance_inflation` fault, no mean shift)
  where Cpk correctly separates two chambers with near-identical means —
  reproducing the Overview's own "平均值正常 ≠ 过程健康" framing end to end.
- 74/74 tests pass repo-wide (8 new), ruff/mypy clean.

### Explicitly not T3

`SPCRunResult.first_alarm_index` is scaffolding, not the Overview section
4.3 detection-scoring API (`event_detected`/`detection_delay`/
`pre_fault_false_alarms`/`missed_event`), which needs the simulator's
hidden-truth fault ground truth compared against detection output — that
comparison is still Gate T3.

## [T2 complete] — 2026-09-12

### Added

- `src/fabtwin/spc/cusum.py`: two-sided CUSUM (S_hi/S_lo). Checked against
  NIST's own 20-point worked example (section 6.3.2.3) — the page was
  re-fetched requesting the full (i, x_i, S_hi, S_lo) table rather than
  trusting a first, possibly-summarized extraction, several points
  hand-recomputed, then all 20 rows pinned as a fixture. Reproduces NIST's
  own conclusion (in control through group 13, signaling from group 14).
- `src/fabtwin/spc/xbar_r.py`: Xbar-R subgroup chart using NIST's real
  published A2/D3/D4 constants table (section 6.3.2.1). **Provenance
  callout**: NIST's handbook does not publish a full numeric worked example
  for this chart (checked both the formula page and the overview page,
  2026-09-12) — the known-answer test uses a small hand-computed,
  hand-verified fixture built from the real constants instead, and says so
  explicitly rather than implying it's a NIST worked example the way
  I-MR/EWMA/CUSUM/capability are.
- `src/fabtwin/spc/rules.py`: the four Western Electric zone rules (1
  point beyond 3σ; 2-of-3 beyond 2σ same side; 4-of-5 beyond 1σ same side;
  8 consecutive same side), each violation carrying `rule_id`,
  `trigger_index`, and `contributing_window`.
- 101/101 tests pass repo-wide (27 new), ruff/mypy clean.

This closes Gate T2's "6 类控制图/规则" set (I-MR, EWMA, Xbar-R, CUSUM,
capability, Western Electric/Nelson rules). Not yet done: no case study has
been run through this layer (Gate T4), and PCA/Hotelling T²/SPE
multivariate monitoring is out of scope here (section 4.5, T3/T4).

## [T3 partial] — 2026-09-12

### Added

- `src/fabtwin/detection.py`: the formal detection-scoring API — the first
  place fault ground truth is allowed to meet SPC detection output, and
  only for after-the-fact scoring, never to influence how a chart's limits
  or points are computed. `score_detection(result, fault)` compares an
  `analysis.py` `SPCRunResult` against a simulator `FaultEvent` and returns
  `event_detected`, `first_alarm_timestamp`, `detection_delay`,
  `pre_fault_false_alarms`, `missed_event`.
- 11 new tests: 8 unit tests on hand-built `SPCRunResult` fixtures
  (no-alarm/missed-event, pre-onset alarm counted as a false alarm not a
  detection, exact-onset edge case, multiple false alarms before a true
  detection, first-vs-later alarm selection), plus 3 integration tests —
  the first time simulator → SPC → detection run together end to end on a
  real chamber-drift scenario.
- 112/112 tests pass repo-wide, ruff/mypy clean.

### Not yet done (T3 remaining)

Yield (measurement/wafer/lot three-level pass definitions) and DPPM
(opportunity count + defect definition, config-driven) — data-dictionary.md
section 8. Do not treat Gate T3 as complete.

## [T1 complete] — 2026-09-21/22

### Added

- `tests/validation/test_variance_decomposition.py`: the third and last of
  Gate T1's own deliverables (Overview section 2: "可复现的 hierarchical
  simulator、数据字典、分布/方差分解验证"). Isolates each random-effect
  layer (lot, wafer, site-noise, tool/chamber offset) through the real
  `simulate()` pipeline and checks empirical variance matches the
  configured sigma; checks combined variance decomposes additively across
  layers; checks variance direction tracks a doubled sigma monotonically.
  6 new tests, 118/118 repo-wide, ruff/mypy clean. **Gate T1's own scope is
  now complete** — simulator, data dictionary, and this validation.

### Fixed

- `README.md` had been stuck at the P0 description ("no simulator/SPC/
  dashboard exist yet", every gate "not started") since before the T1
  commit landed — a real drift bug, not just a missing update, since it's
  the first thing anyone reads. Updated the status line and roadmap table
  to the real per-commit state (T1/T2 ✅, T3 🟡), with an explicit note that
  "✅" means formula-level complete, not "a case study has been run."
- `scripts/validate.py`'s one mandatory check was still the original P0
  placeholder despite `tests/validation` now having 25 real tests. Changed
  it to actually run `pytest tests/validation` and report the genuine
  pass/fail as the check detail — `make validate` now gates on something
  real instead of an unconditional `passed: True`.

### Not yet done (T1 is complete; T2/T3/T4 remaining work is unaffected)

`app/main.py` is still a placeholder page, `make cases` still a stub, and
none of the three frozen case studies have been run — those are Gate T4's
deliverable, not T1's, per the Roadmap table.

## [T2 fix] — 2026-09-22

### Fixed

- The earlier "T2 complete" entry above was wrong: it treated Xbar-R and
  Xbar-S as one item under a "6 类控制图/规则" summary, but the Overview's
  own acceptance criteria (section 4.6) list them separately, and only
  Xbar-R had actually been built. Found when asked what was left for T2 and
  re-checking section 4.6's literal list rather than the roadmap's shorthand
  summary.
- Added `src/fabtwin/spc/xbar_s.py`. Different provenance tier from every
  other chart: NIST's handbook page publishes no c4/A3/B3/B4 constants table
  at all (confirmed while building `xbar_r.py`), so this derives c4(n) from
  its closed-form definition and A3/B3/B4 algebraically from c4, cross-
  checked against commonly published SPC textbook constants for n=5
  (A3=1.427, B3=0.000, B4=2.089 — matches to 3 decimal places).
- 11 new tests, including one proving the actual reason an S chart exists:
  a subgroup with an unchanged mean but a blown-up spread trips the S chart
  while the Xbar chart sees nothing wrong.
- 129/129 tests pass repo-wide (was 118), ruff/mypy clean.

## [T3 yield/DPPM + CUSUM wiring] — 2026-10-07

### Added

- `src/fabtwin/yields.py`: the three-level yield and DPPM from
  `docs/data-dictionary.md` section 8. `measurement_pass` / `wafer_pass` /
  `lot_pass` are separate outputs driven by `YieldConfig` (per-metric spec
  limits, required metrics, required sites, lot threshold). A wafer missing
  any required measurement raises instead of silently passing. `compute_dppm`
  takes `DPPMConfig` with no default denominator (`opportunities_per_wafer`
  and `defect_definition` are required) and uses `defect_count`, never
  spec-limit failures. `wilson_interval` supplies the confidence interval
  Overview 4.4 case 2 asks for on wafer yield.
- `analysis.run_cusum`: CUSUM now returns the same `SPCRunResult` as I-MR and
  EWMA, so `score_detection` scores all three methods through one interface
  (needed for case 1). k and h are given in Phase I sigma multiples and frozen
  as absolute values in `limits.params`.
- 18 new tests (14 yield/DPPM with hand-computed expectations plus a real
  `simulate()` fault scenario, 4 CUSUM). 147/147 pass, ruff/mypy clean.

### Not yet done

- PCA/Hotelling T²/SPE multivariate monitoring (Overview 4.2) is still not
  built; it is the Overview risk-table checkpoint for the end of T3.
- Nothing here has been run through a frozen case study; that is Gate T4.

## [T3 PCA/T2/SPE] - 2026-10-07

### Added

- `src/fabtwin/spc/pca_monitor.py`: PCA monitoring with Hotelling T^2 and SPE,
  Phase I fit / frozen Phase II scoring. Components chosen by a cumulative-variance
  threshold (or fixed `n_components`), always leaving a residual subspace. T^2 limit
  uses the future-observation F form; SPE limit uses Box's weighted chi-square
  approximation. alpha, k, retained variance and both limits are recorded in
  `model.params`.
- `analysis.run_pca_monitor`: per-lot means of several metrics -> same
  `SPCRunResult` as the univariate charts, so `score_detection` scores it too.
- 11 tests: eigenvalues vs an independent correlation-matrix decomposition; T^2 limit
  vs the published F_0.01(2,18)=6.013; SPE limit reduces to lambda*chi2_0.99(3)=11.345
  when residual eigenvalues are equal; healthy false-alarm rate ~ alpha; a
  correlation-breaking fault caught by SPE while I-MR on each variable stays at
  nominal false-alarm level; a mean shift along the dominant direction caught by T^2;
  an end-to-end simulate -> PCA -> detection run. 158/158 pass, ruff/mypy clean.
- One test expectation was initially miscalibrated (a ~2.4 sd shift is not reliably
  caught at alpha=0.01); the shift was corrected, the limit was not touched.

### Not done

- Nothing has been run on a frozen case study or on LAM9600 yet (Gate T4 / Overview 4.5).
  PCA on the simulator's lot means is a plumbing check, not evidence about real
  multi-sensor data.


## [T3 review fixes] - 2026-11-21

Fixes for the six issues the 2026-11-05 T3 review found at `775ce5e` (all existing checks
were green; independent probes found the problems). Data-dictionary changes are in
`docs/adr/0002-t3-review-fixes.md`. Done on macOS (arm64, Python 3.11.16, numpy 2.4.6,
pandas 3.1.1, scipy 1.17.1, pydantic 2.14.4).

### Fixed

1. **Faults on derived metrics did nothing.** `FaultEvent.metric` and the schema now allow
   only `etch_depth`, `cd_bias`, `defect_count`; `etch_rate`/`wiwnu` faults are rejected
   (they are derived from `etch_depth`). Was: 0 rows changed, no error.
2. **Degradation was per hour.** `monotonic_equipment_degradation` now drifts per lot
   processed on the affected chamber (counted by the simulator, never defaulted; first
   affected lot offset 0). Was: identical to `linear_drift`, 0.5 vs 2.0 nm per lot at 30 vs
   120 min spacing; now 1.000 nm per lot at both.
3. **Detection scoring credited the wrong alarms.** Only alarms while the fault is active
   count; later ones go to the new `post_fault_alarms`. Scoring raises if the fault is active
   in Phase I, never active in Phase II, or out of the chart's scope (`SPCRunResult` now
   carries `tool_id`, `chamber_id`, `metrics`; another chamber only with
   `sibling_control=True`). Was: a fault that ended at hour 3 "detected" at hour 20; a fault
   inside Phase I "detected"; a chamber-B fault silently "missed" on chamber A's chart.
4. **`FaultEvent` and its schema were incompatible both ways.** The model accepts the
   schema's nested `affected_scope` (and the flat form), serializes to the schema form, omits
   a missing `description`, and forbids unknown fields. Round-trip tests added.
5. **A `defect_count` fault changed unrelated data.** Each chamber now has its own random
   stream (`SeedSequence([seed, crc32(tool_id), crc32(chamber_id)])`), every draw consumes a
   fixed number of variates, and `defect_count` uses one uniform plus the inverse CDF. Was:
   4912 rows changed across both chambers and all five metrics; now 50 rows, chamber A,
   `defect_count` only. **This changes every seed's output.**
6. **`variance_inflation` scaled site measurement noise.** It now scales the lot and wafer
   sigma (process level, §6); site noise is the measurement layer and is untouched. At x5:
   within-wafer sd 1.90 -> 1.92 (unchanged), lot-mean sd 4.96 -> 22.23.

Also: `run_pca_monitor(statistic="T2"|"SPE"|"either")` names its method `PCA-T2` /
`PCA-SPE` / `PCA-T2-SPE` (§7); fault configs reject non-positive or non-finite variance
factors, a `defect_count` variance factor below 1, non-positive durations, recovery at or
before onset, and non-finite magnitudes; data dictionary §7 says when to use univariate
charts vs PCA; stale "no code implements it yet" / "Empty at P0" text updated.

### Tests changed after seeing them fail (kept for the record)

The new random streams made five existing tests fail. Each was re-examined rather than
re-seeded:

- Three asserted "a healthy sibling chamber never alarms" (I-MR, EWMA, detection
  integration). Over 200 seeds a 3-sigma chart with a 10-lot Phase I shows at least one
  false alarm in 20 lots 27 % (I-MR) / 21 % (EWMA) of the time; the assertion held only for
  seed 42 before. They now require the drifting chamber to alarm on >= 10 of 20 lots and the
  sibling on <= 2, and the sibling-control score to match the sibling's own alarms.
- The PCA end-to-end test asserted the healthy sibling never alarms; the review already
  measured healthy PCA alarms in most runs with a 15-lot Phase I (a T4 risk). It now
  requires the faulted chamber to alarm more than 3x as often.
- The capability test's "means are close" check compared the mean difference with the sigma
  difference. With lot-level variance inflation the Phase I mean is noisier; it now
  compares with the noisy chamber's sigma (0.3 sigma here). The Cpk assertions are unchanged
  (Cpk 4.64 vs 0.57).

189 tests pass, ruff, ruff format, mypy and `validate.py` pass.

### Not done

- Review plan step 5 (dependency lock file, `.gitattributes`, cross-system baseline
  fingerprints, CI matrix): which systems the CI matrix covers is not decided yet.
- T3 milestone stays open until Leo reviews the fixes against Overview §4.3.
- The T4 risks the review listed (PCA healthy false alarms, SPE needing a long Phase I,
  case 2 config, S chart not wired into `analysis.py`, `validate.py` not covering PCA and
  detection scoring) are unchanged; the Cpk-vs-variance numbers need re-measuring now
  that variance inflation acts at the process level.

## [Calibrated limits for a short Phase I] - 2026-11-21

### Added

- `src/fabtwin/spc/calibration.py` and `false_alarm_target=` on `run_imr`, `run_ewma`,
  `run_cusum`, `run_pca_monitor` (opt-in; classical limits stay the default). The limit
  multiplier is chosen so that P(at least one false alarm over the Phase II window) equals
  the target, accounting for the Phase I length: a seeded Monte Carlo for the univariate
  charts (exact under i.i.d. normality, because the estimates are location-scale
  equivariant), a parametric bootstrap for PCA (approximation). Recorded in
  `limits.params["calibration"]`. Decision and trade-offs: `docs/adr/0003`.
- `imr.fit_phase_i(x, k=3.0)`: the multiplier is a parameter (default unchanged).
- `scripts/t4_false_alarm_calibration.py`: measurement on the simulator.
- 12 tests, the key one independent of how the multiplier is computed: fresh data with an
  arbitrary mean and sigma, a different seed and the real chart code give a family-wise
  false-alarm rate within 0.015 of 5 % for I-MR, EWMA and CUSUM.

### Measured (200 seeds; PCA 40; target 5 %)

- Healthy-chamber any-alarm rate, 10-lot Phase I / 20-lot Phase II: I-MR 0.30 -> 0.06,
  EWMA 0.30 -> 0.07, CUSUM 0.32 -> 0.07; PCA (15/25 lots) 0.75 -> 0.07.
- 5 nm/h drift still detected in every run (median delay 1 h; CUSUM 2 h).
- Cost on a small 1 nm step: detection I-MR 0.77 -> 0.34, EWMA 0.95 -> 0.77,
  CUSUM 0.99 -> 0.94, with longer delays (ADR 0003 table).

### Not done

- Not yet used by any case study; normality is assumed (approximation for wiwnu and
  defect_count). SPE's own small-Phase-I bias (review: 9.2 % at 15 lots vs 1 % nominal) is
  absorbed by the PCA bootstrap only in the family-wise sense.
