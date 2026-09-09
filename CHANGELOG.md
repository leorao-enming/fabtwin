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

- SPC/capability layer (Gate T2), fault-ground-truth-vs-detection scoring
  (Gate T3), the three frozen case configs and Streamlit dashboard (Gate
  T4) are all still not started. This simulator has not yet been run
  end-to-end through `make cases` or connected to `app/main.py`.
