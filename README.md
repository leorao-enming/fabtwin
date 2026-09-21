# FabTwin

Hierarchical synthetic plasma-etch process simulator with SPC / process-capability / fault-diagnostics analytics, built to demonstrate semiconductor manufacturing analytics competency.

**Status: Gates T1-T2 complete, T3 in progress.** The simulator, all six SPC/capability chart types, and the core fault-detection-scoring API exist and are tested (see the status table below). No dashboard, case studies, or external validation (SECOM/LAM9600) exist yet. Nothing in this repo should be treated as a working result until a `v1.0.0` tag exists — in particular, no case study has been run yet, so no number here supports a resume claim.

## What this project demonstrates

- Hierarchical process simulation with explicit fixed/random-effect decomposition (recipe, tool/chamber, lot/wafer, drift, noise)
- Statistically correct SPC/capability analysis (Phase I/II separation, I-MR/Xbar/EWMA/CUSUM, Cp/Cpk vs Pp/Ppk) and multivariate monitoring (PCA/Hotelling T²/SPE) where univariate charts don't apply
- Fault injection and detection scoring (detection delay, false alarms, missed events) with honest multi-seed statistics
- External validation against two real public datasets (SECOM, LAM9600) with an explicit audit of common evaluation mistakes in this space, not just another accuracy number

See the full plan and the differentiation rationale in the Obsidian project vault:
- `FabTwin & FabChem Overview.md` (roadmap, gates, engineering contract)
- `FabTwin 差异化维度选择.md` (why the external-validation layer, why multivariate SPC)

## Repository layout

```text
src/fabtwin/      # computation core, application services, I/O schema — no UI logic here
app/              # Streamlit dashboard; reads results via the service layer only
configs/          # baseline / fault / case configs (version-controlled)
tests/unit/       # fast, no network — single function / formula tests
tests/validation/ # known-answer tests, fixture comparisons, balance checks
cases/            # frozen case-study inputs, results, figures, short conclusions
docs/             # architecture notes, ADRs, assumptions, report source, interview pack
evidence/         # machine-readable validation-summary + run manifests
scripts/          # reproduce_cases, export_figures, build_report
```

## Commands

```bash
make setup     # create venv, install project + dev deps
make test      # fast unit tests, no network — PR gate
make validate  # run engineering validation, write evidence/validation-summary.json
make cases     # rebuild all frozen case tables/figures from configs
make app       # run the Streamlit dashboard
make report    # build the technical report from evidence + cases only
```

`make validate` and `make cases` are the only commands allowed to produce numbers referenced in the report, README, or resume bullets — nothing here is hand-edited after the fact.

## Status against the roadmap

| Gate | Deliverable | Status |
|---|---|---|
| P0 | Repo skeleton, ADR template, CI empty-run | ✅ `73323d1` |
| T1 | Simulator + data dictionary + variance-decomposition validation | ✅ `a710bcf` |
| T2 | SPC + capability (I-MR, EWMA, Xbar-R, CUSUM, Cp/Cpk/Pp/Ppk, Western Electric/Nelson rules) | ✅ `18d977b` |
| T3 | Fault detection scoring (event_detected/detection_delay/false alarms) | 🟡 in progress — yield/DPPM not yet built |
| T4 | Demo + 3 cases + external validation (SECOM/LAM9600) | ⬜ not started |
| T5 | v1.0.0 release | ⬜ not started |

"✅" means the gate's own listed deliverable is implemented and tested (see `CHANGELOG.md` for exactly what shipped in which commit) — it does **not** mean a case study has been run through it yet. Every chart/capability formula (T2) is checked against a real NIST Engineering Statistics Handbook worked example, not just internal self-consistency; the one exception (Xbar-R, where NIST doesn't publish a full numeric example) is checked against a hand-verified fixture built from NIST's own published control-chart constants, and says so explicitly in its test file rather than implying otherwise.

## Non-goals (v1)

Accounts, databases, cloud deployment, real-time streaming, ML anomaly detection in place of statistical methods, 3D digital twin. See the risk table in the Overview doc for what gets cut first if a gate slips.

## License

MIT — see `LICENSE`.
