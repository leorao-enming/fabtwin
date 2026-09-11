"""Exponentially Weighted Moving Average (EWMA) control chart.

Reference: NIST Engineering Statistics Handbook, section 6.3.2.4, "EWMA
Control Charts" (https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm).
Known-answer test: tests/validation/test_ewma_nist.py, verified against the
NIST worked example's full EWMA_0..EWMA_20 table (re-fetched and hand
cross-checked point by point, not taken from a first, ambiguous extraction -
see the test file's docstring).

Indexing convention (must match the NIST page, not a guess): EWMA_0 = target
(the seed, before any observation). EWMA_t = lambda*X_t + (1-lambda)*EWMA_(t-1)
for t = 1..n, using EWMA_t paired with X_t. ewma_series() below returns
[EWMA_0, EWMA_1, ..., EWMA_n] - n+1 values for n observations.
"""

from __future__ import annotations

from fabtwin.spc.phase import ChartPoint, FrozenLimits


def ewma_series(x: list[float], target: float, lam: float) -> list[float]:
    if not 0 < lam <= 1:
        raise ValueError(f"lambda must be in (0, 1], got {lam}")
    series = [target]
    for xi in x:
        series.append(lam * xi + (1 - lam) * series[-1])
    return series


def fit_phase_i(target: float, sigma: float, lam: float, l_factor: float = 3.0) -> FrozenLimits:
    """Control limits per NIST: UCL/LCL = target +/- L*sigma*sqrt(lambda/(2-lambda))."""
    if not 0 < lam <= 1:
        raise ValueError(f"lambda must be in (0, 1], got {lam}")
    width_factor = (lam / (2 - lam)) ** 0.5
    return FrozenLimits(
        center_line=target,
        ucl=target + l_factor * width_factor * sigma,
        lcl=target - l_factor * width_factor * sigma,
        method="EWMA",
        params={"lambda": lam, "L": l_factor, "target": target, "sigma": sigma},
    )


def apply_phase_ii(x: list[float], limits: FrozenLimits) -> list[ChartPoint]:
    lam = limits.params["lambda"]
    series = ewma_series(x, limits.params["target"], lam)[1:]  # drop EWMA_0 seed, one point per x
    return [
        ChartPoint(index=i, value=v, out_of_control=(v > limits.ucl or v < limits.lcl))
        for i, v in enumerate(series)
    ]
