# ADR 0003: Control limits calibrated for a short Phase I

- **Status:** accepted (opt-in; classical limits stay the default)
- **Date:** 2026-11-21
- **Gate:** T3 / T4

## Context

The 2026-11-05 T3 review and the ADR 0002 test changes measured how often a *healthy*
chamber alarms when limits come from a short Phase I: with 10 Phase I lots and 20 Phase II
lots, 27-32 % of runs show at least one false alarm for I-MR, EWMA and CUSUM, and 75 % for
PCA T^2/SPE with a 15-lot Phase I. With known parameters the I-MR figure would be about
5 %. The cause is estimation error: the classical multipliers (3 sigma, L = 3, h = 5 sigma,
alpha-level T^2/SPE limits) treat Phase I estimates as true values, and an underestimated
sigma narrows every limit. Case studies (T4) report false-alarm counts, so this would make
every chart look worse than it is and every comparison noisy.

## Decision

Add opt-in calibrated limits (`false_alarm_target=` on `run_imr`, `run_ewma`, `run_cusum`,
`run_pca_monitor`; `spc/calibration.py`). The multiplier is chosen so that the probability
of **at least one false alarm over the Phase II window** equals the target:

- I-MR, EWMA, CUSUM: the Phase I mean and moving-range sigma are location-scale
  equivariant, so for in-control i.i.d. normal data the chart statistic in estimate units
  depends only on (Phase I length, horizon, lambda / k). A seeded Monte Carlo (20 000 runs)
  gives the multiplier exactly, without knowing the process mean or sigma.
- PCA: not invariant in the same way; a parametric bootstrap from the Phase I correlation
  matrix (4 000 runs, model refitted each time) gives a common factor on both limit ratios.
  Recorded as an approximation.

Every calibrated result stores the multiplier, target, Phase I length, horizon, simulation
count and seed in `FrozenLimits.params["calibration"]`. Classical limits remain the default,
so the NIST known-answer tests are unchanged.

## Alternatives considered

- **Longer Phase I only** - correct in principle and still recommended, but case 3 and the
  LAM9600 data (about 36 healthy wafers per experiment) cannot always supply it.
- **Bonferroni on alpha** - ignores the estimation error, which is the actual cause.
- **Conditional (guaranteed-performance) bootstrap limits** - controls the rate for the
  Phase I sample actually observed, at more cost and complexity; possible later.

## Consequences

Measured on the simulator (scripts/t4_false_alarm_calibration.py, 200 seeds; PCA 40), target 5 %:

| scenario | chart | healthy any-alarm rate | detected | median delay |
|---|---|---|---|---|
| 5 nm/h drift | I-MR | 0.30 -> 0.06 | 1.00 -> 1.00 | 1 h -> 1 h |
| | EWMA | 0.30 -> 0.07 | 1.00 -> 1.00 | 1 h -> 1 h |
| | CUSUM | 0.32 -> 0.07 | 1.00 -> 1.00 | 1 h -> 2 h |
| 1 nm step | I-MR | 0.30 -> 0.06 | 0.77 -> 0.34 | 2 h -> 4.5 h |
| | EWMA | 0.30 -> 0.07 | 0.95 -> 0.77 | 2 h -> 5 h |
| | CUSUM | 0.32 -> 0.07 | 0.99 -> 0.94 | 3 h -> 7 h |
| 8 nm step, PCA (etch_depth, cd_bias, wiwnu) | T2/SPE | 0.75 -> 0.07 | 1.00 -> 1.00 | - |

The honest downside: fewer false alarms buy less sensitivity to small shifts, most for
I-MR; EWMA and CUSUM keep most of theirs. The rate is a family-wise rate averaged over
Phase I samples; a particular Phase I can still be unlucky. Normality is assumed; for
wiwnu and defect_count the calibration is an approximation to be checked per case.

## Rollback trigger

If a case study shows the calibrated rate far from the target on its own data (checked by
simulation of that case's healthy runs), or the loss of small-shift sensitivity hides a
fault the case is designed to show, report both limit types side by side and revisit this
ADR rather than switching silently.
