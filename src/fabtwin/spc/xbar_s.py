"""Xbar-S (subgroup mean and standard deviation) control chart.

Overview section 4.6 lists Xbar-S as a distinct required chart from Xbar-R
("与手算或独立 fixture 一致：I-MR、Xbar-R、Xbar-S、EWMA、CUSUM、Cp/Cpk/Pp/Ppk") -
it is not satisfied by Xbar-R alone. Overview section 6.3.1.1 of the NIST
handbook recommends S over R for subgroup sizes above ~10 and notes S is
always the statistically more efficient estimator; both charts exist here
because the Overview names both explicitly, not because one subsumes the
other operationally.

PROVENANCE NOTE (different tier from every other chart in this package):
unlike Xbar-R, whose A2/D3/D4 constants are NIST's own published table
(xbar_r.py), NIST's handbook page for this section explicitly does NOT
publish c4/A3/B3/B4 (confirmed 2026-09-12 while building xbar_r.py - the
same fetch that found no worked example for Xbar-R found no S-chart
constants table either, on the same page). Rather than transcribe a
constants table from an unverified secondary source, this module computes
c4(n) directly from its closed-form definition - the unbiasing constant for
the sample standard deviation of an n-sample from a normal distribution:

    c4(n) = sqrt(2/(n-1)) * Gamma(n/2) / Gamma((n-1)/2)

and derives A3/B3/B4 algebraically from c4, per the standard relations
(e.g. Montgomery, "Introduction to Statistical Quality Control"):

    A3(n) = 3 / (c4(n) * sqrt(n))
    B3(n) = max(0, 1 - 3*sqrt(1-c4(n)^2)/c4(n))
    B4(n) = 1 + 3*sqrt(1-c4(n)^2)/c4(n)

This is provably exact (a closed-form mathematical definition, not a
looked-up table that could carry a transcription error) and cross-checks
against the commonly published values for n=5 (A3=1.427, B3=0, B4=2.089) -
see tests/validation/test_xbar_s_derivation.py for both the derivation
check and a hand-computed known-answer fixture.

Overview section 4.2: "Xbar-R/Xbar-S 只在 subgroup 定义合理且大小一致时启用" -
fit_phase_i() enforces equal subgroup sizes and rejects n<2 (no standard
deviation is defined for a subgroup of 1).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from fabtwin.spc.phase import ChartPoint, FrozenLimits


def c4(n: int) -> float:
    """Unbiasing constant for the sample standard deviation, n>=2."""
    if n < 2:
        raise ValueError("c4 is undefined for n<2 (no standard deviation for a single point)")
    return math.sqrt(2 / (n - 1)) * math.gamma(n / 2) / math.gamma((n - 1) / 2)


def subgroup_constants(n: int) -> tuple[float, float, float]:
    """Returns (A3, B3, B4) for subgroup size n, derived from c4(n)."""
    c = c4(n)
    spread = 3 * math.sqrt(1 - c**2) / c
    a3 = 3 / (c * math.sqrt(n))
    b3 = max(0.0, 1 - spread)
    b4 = 1 + spread
    return a3, b3, b4


@dataclass(frozen=True)
class XbarSLimits:
    xbar_limits: FrozenLimits
    s_limits: FrozenLimits
    n: int


def _validate_equal_subgroup_size(subgroups: list[list[float]]) -> int:
    sizes = {len(g) for g in subgroups}
    if len(sizes) != 1:
        raise ValueError(
            f"all subgroups must be the same size for a valid Xbar-S chart, "
            f"got sizes {sorted(sizes)}"
        )
    n = sizes.pop()
    if n < 2:
        raise ValueError("subgroup size must be >= 2 - stdev is undefined for a single point")
    return n


def fit_phase_i(subgroups: list[list[float]]) -> XbarSLimits:
    if len(subgroups) < 2:
        raise ValueError("Phase I Xbar-S fit needs at least 2 subgroups")
    n = _validate_equal_subgroup_size(subgroups)
    a3, b3, b4 = subgroup_constants(n)

    means = [sum(g) / n for g in subgroups]
    stdevs = [statistics.stdev(g) for g in subgroups]
    xbar_bar = sum(means) / len(means)
    s_bar = sum(stdevs) / len(stdevs)

    xbar_limits = FrozenLimits(
        center_line=xbar_bar,
        ucl=xbar_bar + a3 * s_bar,
        lcl=xbar_bar - a3 * s_bar,
        method=f"Xbar (n={n})",
        params={"A3": a3, "s_bar": s_bar, "n": n},
    )
    s_limits = FrozenLimits(
        center_line=s_bar,
        ucl=b4 * s_bar,
        lcl=b3 * s_bar,
        method=f"S (n={n})",
        params={"B3": b3, "B4": b4, "n": n},
    )
    return XbarSLimits(xbar_limits=xbar_limits, s_limits=s_limits, n=n)


def apply_phase_ii(
    subgroups: list[list[float]], limits: XbarSLimits
) -> tuple[list[ChartPoint], list[ChartPoint]]:
    sizes = {len(g) for g in subgroups}
    if sizes != {limits.n}:
        raise ValueError(
            f"Phase II subgroups must all have size n={limits.n} to match the frozen limits, "
            f"got sizes {sorted(sizes)}"
        )
    means = [sum(g) / limits.n for g in subgroups]
    stdevs = [statistics.stdev(g) for g in subgroups]

    xbar_points = [
        ChartPoint(i, v, v > limits.xbar_limits.ucl or v < limits.xbar_limits.lcl)
        for i, v in enumerate(means)
    ]
    s_points = [
        ChartPoint(i, v, v > limits.s_limits.ucl or v < limits.s_limits.lcl)
        for i, v in enumerate(stdevs)
    ]
    return xbar_points, s_points
