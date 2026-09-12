"""Xbar-R (subgroup mean and range) control chart.

Control-chart constants (A2, D3, D4) are NIST's own published table for
subgroup sizes n=2..10, from the NIST Engineering Statistics Handbook,
section 6.3.2.1, "Shewhart X-bar and R and S Control Charts"
(https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc321.htm), used
verbatim below.

PROVENANCE NOTE: unlike I-MR/EWMA/CUSUM/capability, the NIST handbook does
NOT publish a full numeric worked example for this chart - both the
constants page and the chart-overview page were fetched (2026-09-12) and
neither has one. Per Overview section 4.6's "与手算或独立 fixture 一致"
allowance (an independent hand-verified fixture is an accepted alternative
to a NIST worked example, not just a NIST worked example itself), the
known-answer test in tests/validation/test_xbar_r_nist_constants.py uses a small,
hand-computed fixture built from these NIST-sourced constants - this is
recorded explicitly there, not glossed over as "NIST-verified" the way the
other three charts are.

Overview section 4.2: "Xbar-R/Xbar-S 只在 subgroup 定义合理且大小一致时启用" -
fit_phase_i() enforces equal subgroup sizes and rejects the degenerate
n<2 case (no range is defined for a subgroup of 1).
"""

from __future__ import annotations

from dataclasses import dataclass

from fabtwin.spc.phase import ChartPoint, FrozenLimits

# NIST-published A2/D3/D4 by subgroup size n, section 6.3.2.1 constants table.
_A2_D3_D4: dict[int, tuple[float, float, float]] = {
    2: (1.880, 0.0, 3.267),
    3: (1.023, 0.0, 2.575),
    4: (0.729, 0.0, 2.282),
    5: (0.577, 0.0, 2.115),
    6: (0.483, 0.0, 2.004),
    7: (0.419, 0.076, 1.924),
    8: (0.373, 0.136, 1.864),
    9: (0.337, 0.184, 1.816),
    10: (0.308, 0.223, 1.777),
}


def subgroup_constants(n: int) -> tuple[float, float, float]:
    """Returns (A2, D3, D4) for subgroup size n."""
    if n not in _A2_D3_D4:
        raise ValueError(
            f"no NIST A2/D3/D4 constant for subgroup size n={n} - published range is 2..10"
        )
    return _A2_D3_D4[n]


@dataclass(frozen=True)
class XbarRLimits:
    xbar_limits: FrozenLimits
    r_limits: FrozenLimits
    n: int


def _validate_equal_subgroup_size(subgroups: list[list[float]]) -> int:
    sizes = {len(g) for g in subgroups}
    if len(sizes) != 1:
        raise ValueError(
            f"all subgroups must be the same size for a valid Xbar-R chart, "
            f"got sizes {sorted(sizes)}"
        )
    n = sizes.pop()
    if n < 2:
        raise ValueError("subgroup size must be >= 2 - a range is undefined for a single point")
    return n


def fit_phase_i(subgroups: list[list[float]]) -> XbarRLimits:
    if len(subgroups) < 2:
        raise ValueError("Phase I Xbar-R fit needs at least 2 subgroups")
    n = _validate_equal_subgroup_size(subgroups)
    a2, d3, d4 = subgroup_constants(n)

    means = [sum(g) / n for g in subgroups]
    ranges = [max(g) - min(g) for g in subgroups]
    xbar_bar = sum(means) / len(means)
    r_bar = sum(ranges) / len(ranges)

    xbar_limits = FrozenLimits(
        center_line=xbar_bar,
        ucl=xbar_bar + a2 * r_bar,
        lcl=xbar_bar - a2 * r_bar,
        method=f"Xbar (n={n})",
        params={"A2": a2, "r_bar": r_bar, "n": n},
    )
    r_limits = FrozenLimits(
        center_line=r_bar,
        ucl=d4 * r_bar,
        lcl=d3 * r_bar,
        method=f"R (n={n})",
        params={"D3": d3, "D4": d4, "n": n},
    )
    return XbarRLimits(xbar_limits=xbar_limits, r_limits=r_limits, n=n)


def apply_phase_ii(
    subgroups: list[list[float]], limits: XbarRLimits
) -> tuple[list[ChartPoint], list[ChartPoint]]:
    sizes = {len(g) for g in subgroups}
    if sizes != {limits.n}:
        raise ValueError(
            f"Phase II subgroups must all have size n={limits.n} to match the frozen limits, "
            f"got sizes {sorted(sizes)}"
        )
    means = [sum(g) / limits.n for g in subgroups]
    ranges = [max(g) - min(g) for g in subgroups]

    xbar_points = [
        ChartPoint(i, v, v > limits.xbar_limits.ucl or v < limits.xbar_limits.lcl)
        for i, v in enumerate(means)
    ]
    r_points = [
        ChartPoint(i, v, v > limits.r_limits.ucl or v < limits.r_limits.lcl)
        for i, v in enumerate(ranges)
    ]
    return xbar_points, r_points
