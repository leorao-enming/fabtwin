# FabTwin v1 Data Dictionary

**Status:** locked at P0 (2026-09-08) as the contract for Gate T1 (simulator) and
Gate T2 (SPC/capability). Changing any field name, unit, or hierarchy level after
T1 implementation starts requires an ADR, not a silent edit.

This is a specification document — no code in this repo implements it yet. It
exists so the simulator (T1), SPC/capability layer (T2), fault/yield scoring
(T3), and the three case studies (4.4) are all built against the same contract
instead of drifting apart.

---

## 1. Process hierarchy

Synthetic **plasma etch** process, locked per Overview §4.1.

```text
tool          — a physical etch tool, tool_id (e.g. "TOOL-01")
  chamber     — a process chamber within a tool, chamber_id (e.g. "CH-A")
                v1 default: 2 chambers per tool (minimum needed for case 2,
                the tool/chamber comparison)
    lot       — a group of wafers processed together, lot_id
                v1 default lot size: 25 wafers (standard FOUP/lot convention)
      wafer   — wafer_id, unique within a lot
        site  — a measurement location on a wafer, site_id
                v1 default: 5-point pattern (center + N/E/S/W at a fixed
                radius fraction of wafer radius)
```

Cardinalities above are v1 defaults, set in `configs/` (T1), not hardcoded in
the simulator — but the **hierarchy levels themselves** (tool → chamber → lot
→ wafer → site) are locked and must not change without an ADR.

## 2. Recipe / setpoints

A `recipe_id` maps to a fixed set of process setpoints. v1 keeps this
intentionally small (four knobs) — this is a synthetic process, not a real
etch recipe, and the point is to have *something* the fixed-effect layer of
the simulator responds to, not to be industrially realistic:

| field | unit | notes |
|---|---|---|
| `rf_power_w` | W | RF power setpoint |
| `pressure_mtorr` | mTorr | chamber pressure setpoint |
| `gas_flow_sccm` | sccm | process gas flow setpoint |
| `etch_time_s` | s | programmed etch time |

## 3. Output metrics (v1: five, per Overview §4.1)

| metric | unit | level | definition |
|---|---|---|---|
| `etch_depth` | nm | site | measured post-etch depth at a site |
| `etch_rate` | nm/min | site | `etch_depth / etch_time_s * 60` |
| `cd_bias` | nm | site | post-etch critical dimension − target CD |
| `wiwnu` | % | wafer | within-wafer non-uniformity, SEMI-style: `(max(etch_depth) − min(etch_depth)) / (2 × mean(etch_depth)) × 100` across all sites on one wafer |
| `defect_count` | count (int ≥ 0) | wafer | total inspected defects on a wafer |

`etch_depth`, `etch_rate`, and `cd_bias` are **site-level** (one value per
site per wafer). `wiwnu` is a **derived wafer-level** statistic computed from
a wafer's site-level `etch_depth` values — it is not independently simulated.
`defect_count` is generated at the wafer level directly.

## 4. Observation record schema

Long format — one row per metric per site (or per wafer, for wafer-level
metrics). Machine-readable schema: [`docs/schemas/observation.schema.json`](schemas/observation.schema.json).

Required fields (per Overview §4.1): `timestamp, tool_id, chamber_id, lot_id,
wafer_id, site_id, recipe_id, metric, value, unit`.

`site_id` is `null` for wafer-level metrics (`wiwnu`, `defect_count`).

This is the **only** table analysis code (SPC, capability, dashboards) is
allowed to read. Hidden ground truth (§5) is never exposed to it.

## 5. Hidden ground truth / random-effect decomposition

Per Overview §4.1, the simulator must explicitly separate these contributions
to every generated value, each independently controlled by `configs/` and a
random seed:

1. **Fixed recipe effect** — deterministic function of `recipe_id` setpoints.
2. **Tool/chamber random effect** — a per-`(tool_id, chamber_id)` offset,
   drawn once per simulation run from a configured distribution.
3. **Lot/wafer effect** — per-lot and per-wafer nested random effects.
4. **Time-dependent drift/degradation** — deterministic or fault-driven trend
   over time (see §6); this is where fault schedules act.
5. **Measurement noise** — i.i.d. noise added at the observation stage
   (distinct from process-level variation; this is where `sensor_bias`
   faults act, since a sensor fault corrupts the measurement, not the
   underlying process state).

This decomposition, plus fault ground-truth labels, is written to a
**separate hidden-truth table**, never merged into the observation table
analysis code reads — this is what makes Phase I/II SPC validation and
detection scoring honest (Overview §4.2, §4.6: "fault ground truth 单独保存，
避免分析代码偷看标签").

## 6. Fault event schema

Five fault types, all implemented as composable schedules (Overview §4.3).
Machine-readable schema: [`docs/schemas/fault-event.schema.json`](schemas/fault-event.schema.json).

| `fault_type` | `magnitude` interpretation |
|---|---|
| `step_mean_shift` | additive shift applied to the affected metric from onset, constant while active |
| `linear_drift` | rate of change per hour, applied to the affected metric from onset |
| `variance_inflation` | multiplicative factor on the process-level sigma of the affected metric |
| `sensor_bias` | additive offset applied at the **measurement** stage (§5 item 5), not the process stage — the underlying process is unaffected |
| `monotonic_equipment_degradation` | rate of monotonic drift per wafer (or per lot) processed on the affected `(tool_id, chamber_id)`, until a `recovery_action` resets it |

Every fault event has: `event_id, fault_type, onset (timestamp), duration_s
(nullable — null means "ongoing until recovery_action"), affected_scope
{tool_id, chamber_id (nullable = whole tool), metric}, magnitude,
recovery_action (nullable) {timestamp, action_type, description}`.

## 7. Detection scoring fields

Computed per `(event_id, method)` pair once T2/T3 land — a method is e.g.
`I-MR`, `EWMA`, `CUSUM`, `PCA-T2`, `PCA-SPE`:

- `event_detected` (bool)
- `first_alarm_timestamp` (nullable)
- `detection_delay` (nullable — time or sample count from `onset` to `first_alarm_timestamp`)
- `pre_fault_false_alarms` (int ≥ 0 — alarms raised in the Phase II window before `onset`)
- `missed_event` (bool — true iff `event_detected` is false)

## 8. Yield and DPPM definitions (three-level, per Overview §4.3)

Yield is **not** a single number — three explicit levels, each with its own
config-driven pass rule so they can never silently collapse into each other:

| level | rule | config-driven? |
|---|---|---|
| `measurement_pass` | one `(observation, spec_limit)` pair is within spec | spec limits per metric, in `configs/` |
| `wafer_pass` | v1 default rule: **all** required `(site, metric)` measurements on the wafer pass | which metrics/sites are "required" is config-driven |
| `lot_pass` | v1 default rule: fraction of wafers passing ≥ threshold (default threshold: 100%, overridable) | threshold is config-driven |

**DPPM** uses `defect_count` (§3), not spec-limit measurement failures — these
are deliberately kept separate (Overview §4.3: "Yield 明确定义三级口径... DPPM
的机会数和 defect definition 写入 config，避免把不同分母混为一谈"). Both the
opportunity count (e.g. sites × inspected-metric-count per wafer) and the
defect definition threshold must be recorded in `configs/` — DPPM is never
computed from an implicit/hardcoded denominator.

## 9. Open items (not yet decided — `planned`, resolved at T1 config-authoring time)

- Exact per-metric distribution families and default parameter values for
  each random-effect layer in §5 (e.g. normal vs. lognormal for
  `variance_inflation`).
- Exact site coordinates for the 5-point pattern (radius fraction).
- Whether `defect_count` v1 uses a simple Poisson generator or something
  fault-scope-aware from the start (Overview only requires it exist as an
  output metric at T1; defect *modeling* fidelity can grow at T3).

These are implementation-time decisions for T1/T3, not schema-level
decisions — changing them does not require an ADR the way §1–§8 do.
