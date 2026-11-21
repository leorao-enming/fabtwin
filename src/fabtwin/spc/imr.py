"""Individuals (X) and Moving Range control chart.

Reference: NIST Engineering Statistics Handbook, section 6.3.2.2,
"Individuals Control Charts"
(https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm).
Known-answer test: tests/validation/test_imr_nist.py.
"""

from __future__ import annotations

from fabtwin.spc.phase import ChartPoint, FrozenLimits

D2_N2 = 1.128  # d2 constant for a moving range of consecutive individuals (subgroup size 2)


def moving_ranges(x: list[float]) -> list[float]:
    return [abs(x[i] - x[i - 1]) for i in range(1, len(x))]


def fit_phase_i(x: list[float], k: float = 3.0) -> FrozenLimits:
    """Estimate I-MR center line and k-sigma control limits from Phase I data.

    sigma_hat = MRbar / d2, limits = xbar +/- k*sigma_hat, per the NIST
    reference above (k = 3). A different k comes from spc/calibration.py when the
    limits must account for a short Phase I.
    """
    if len(x) < 2:
        raise ValueError("Phase I I-MR fit needs at least 2 observations (>=1 moving range)")
    mr = moving_ranges(x)
    mr_bar = sum(mr) / len(mr)
    xbar = sum(x) / len(x)
    sigma_hat = mr_bar / D2_N2
    return FrozenLimits(
        center_line=xbar,
        ucl=xbar + k * sigma_hat,
        lcl=xbar - k * sigma_hat,
        method="I-MR",
        params={"mr_bar": mr_bar, "d2": D2_N2, "sigma_hat": sigma_hat, "k": k},
    )


def apply_phase_ii(x: list[float], limits: FrozenLimits) -> list[ChartPoint]:
    return [
        ChartPoint(index=i, value=v, out_of_control=(v > limits.ucl or v < limits.lcl))
        for i, v in enumerate(x)
    ]
