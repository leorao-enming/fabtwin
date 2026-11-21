"""Derived-metric computations - docs/data-dictionary.md section 3.

etch_rate and wiwnu are NOT independently simulated; they are computed from
etch_depth per the locked formulas. defect_count is generated directly at
the wafer level (data dictionary section 9: "simple Poisson generator" for
v1, fault-scope-aware from T3 onward - this module already threads fault
deltas through, but the distributional fidelity stays intentionally simple).
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def etch_rate_from_depth(etch_depth_nm: float, etch_time_s: float) -> float:
    return etch_depth_nm / etch_time_s * 60.0


def wiwnu_from_site_depths(site_depths_nm: list[float]) -> float:
    """SEMI-style within-wafer non-uniformity, data dictionary section 3."""
    if not site_depths_nm:
        return 0.0
    mean = sum(site_depths_nm) / len(site_depths_nm)
    if mean == 0:
        return 0.0
    return (max(site_depths_nm) - min(site_depths_nm)) / (2 * mean) * 100.0


def defect_count_for_wafer(
    rng: np.random.Generator,
    *,
    base_rate: float,
    fault_delta: float = 0.0,
    variance_multiplier: float = 1.0,
    sensor_bias: float = 0.0,
) -> int:
    """v1 simple generator per docs/data-dictionary.md section 9 open item.

    step_mean_shift / linear_drift / monotonic_equipment_degradation faults
    on defect_count shift the Poisson mean (fault_delta, floored so the mean
    never goes negative). variance_inflation switches to a Gamma-Poisson
    mixture (negative binomial) with matching mean but inflated variance,
    since a plain Poisson has no free variance parameter to inflate.
    sensor_bias is applied last as an integer offset to the reported count,
    representing a miscalibrated inspection step rather than a real defect.

    Exactly one uniform variate is drawn per call and turned into a count by
    the inverse CDF. Poisson/negative-binomial samplers consume a varying
    number of variates depending on the mean, which made a defect_count fault
    change every later value in the stream (ADR 0002, issue 5).
    """
    u = rng.random()
    mean = max(0.0, base_rate + fault_delta)
    if mean == 0.0:
        count = 0
    elif variance_multiplier > 1.0:
        # Negative binomial with mean m and variance k*m (k = variance_multiplier):
        # variance = m + m^2/r  =>  r = m / (k - 1)
        r = mean / (variance_multiplier - 1.0)
        p = r / (r + mean)
        count = int(stats.nbinom.ppf(u, r, p))
    else:
        count = int(stats.poisson.ppf(u, mean))
    count = max(0, count)
    count = int(count + round(sensor_bias))
    return max(0, count)
