"""CUSUM (cumulative sum) control chart, two-sided.

Reference: NIST Engineering Statistics Handbook, section 6.3.2.3, "CUSUM
Control Charts" (https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm).
Known-answer test: tests/validation/test_cusum_nist.py, against NIST's own
20-point worked example (target=325, k=0.3175, h=4.1959) - the page was
fetched a second time requesting the full (i, x_i, S_hi, S_lo) table and
several points hand-verified by recomputing the recursion, same discipline
as ewma.py's fixture (see that module's docstring for why this matters).
"""

from __future__ import annotations

from dataclasses import dataclass

from fabtwin.spc.phase import FrozenLimits


@dataclass(frozen=True)
class CusumPoint:
    index: int
    x: float
    s_hi: float
    s_lo: float
    out_of_control: bool


def fit_phase_i(target: float, k: float, h: float) -> FrozenLimits:
    """CUSUM does not have a single "center +/- limit" the way I-MR/EWMA
    do - target/k/h ARE the frozen parameters (Overview 4.2: "lambda/L/k/h/
    target 全部写入结果元数据"). center_line=target, ucl=h, lcl=-h by
    convention only, so CUSUM still fits the shared FrozenLimits shape the
    other chart modules use - apply_phase_ii() below does not use ucl/lcl
    directly, it reads k/h back out of params.
    """
    return FrozenLimits(
        center_line=target,
        ucl=h,
        lcl=-h,
        method="CUSUM",
        params={"target": target, "k": k, "h": h},
    )


def apply_phase_ii(x: list[float], limits: FrozenLimits) -> list[CusumPoint]:
    target = limits.params["target"]
    k = limits.params["k"]
    h = limits.params["h"]

    points: list[CusumPoint] = []
    s_hi = 0.0
    s_lo = 0.0
    for i, xi in enumerate(x):
        s_hi = max(0.0, s_hi + xi - target - k)
        s_lo = max(0.0, s_lo + target - k - xi)
        out_of_control = s_hi > h or s_lo > h
        points.append(
            CusumPoint(index=i, x=xi, s_hi=s_hi, s_lo=s_lo, out_of_control=out_of_control)
        )
    return points
