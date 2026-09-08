# FabTwin

Hierarchical synthetic plasma-etch process simulator with SPC / process-capability / fault-diagnostics analytics, built to demonstrate semiconductor manufacturing analytics competency.

**Status: P0 skeleton.** No simulator, SPC methods, or dashboard exist yet. Nothing in this repo should be treated as a working result until a `v1.0.0` tag exists.

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
| P0 | Repo skeleton, ADR template, CI empty-run | ✅ this commit |
| T1 | Simulator + data dictionary | ⬜ not started |
| T2 | SPC + capability | ⬜ not started |
| T3 | Faults + yield | ⬜ not started |
| T4 | Demo + 3 cases + external validation (SECOM/LAM9600) | ⬜ not started |
| T5 | v1.0.0 release | ⬜ not started |

## Non-goals (v1)

Accounts, databases, cloud deployment, real-time streaming, ML anomaly detection in place of statistical methods, 3D digital twin. See the risk table in the Overview doc for what gets cut first if a gate slips.

## License

MIT — see `LICENSE`.
