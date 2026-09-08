# Docs

- `adr/` — architecture decision records, one file per non-obvious engineering
  decision (why a method was chosen, why a scope was cut). Mirrors the decision
  discipline already used in the project's planning vault.
- Architecture notes, assumption tables, report source (feeds `make report`),
  and the interview package (30s/2min/5min pitches + Q&A cards) will live here
  starting at Gate T4-T5.

Empty of real content at P0 beyond the ADR template.

## Why there is no ADR-0001 here

fabchem-optimizer's `docs/adr/0001-c0-feasibility-spike.md` exists because IDAES/IPOPT
is a heavy, compiled external dependency with known cross-platform install instability —
Overview §8 flags it as the single highest-risk item in either project and pulls its
verification forward to before any flowsheet code is written. FabTwin has no equivalent
external-dependency risk: its stack (numpy/scipy/pandas/Streamlit) installs reliably from
standard wheels. FabTwin's highest-risk items (real-data validation layer schedule risk,
multivariate SPC implementation delay — Overview §8) are scope/schedule risks, not
installation risks, and are already covered by the rollback plans in
`FabTwin 差异化维度选择.md`. No early-spike ADR is warranted; this note documents that
conclusion explicitly rather than leaving it unstated.
