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
