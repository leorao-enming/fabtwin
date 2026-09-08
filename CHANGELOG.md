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
