"""Process capability indices - Cp/Cpk (within/common-cause sigma) and
Pp/Ppk (overall sigma), kept explicitly distinct per Overview section 4.2.

Reference: NIST Engineering Statistics Handbook, section 6.1.6, "Process
Capability Indices" (https://www.itl.nist.gov/div898/handbook/pmc/section1/pmc16.htm).
Known-answer test: tests/validation/test_capability_nist.py, against the
NIST worked example (USL=20, LSL=8, mean=16, s=2 -> Cp=1.0, Cpk=0.6667).

Both cp_cpk() and pp_ppk() share the same underlying formula and differ
only in which sigma estimate the caller supplies - see sigma_within() and
sigma_overall() below for the two estimators. A caller must not pass a
moving-range-based sigma into pp_ppk() or a plain sample-stdev sigma into
cp_cpk(); nothing in the type system prevents that mixup, so the
sigma_kind field on the result exists specifically so a caller/test can
check which one was actually used.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from fabtwin.spc.imr import D2_N2, moving_ranges

MIN_SAMPLE_SIZE = 30  # v1 threshold - see docstring on _capability_from_sigma


@dataclass(frozen=True)
class CapabilityResult:
    cp_or_pp: float
    cpk_or_ppk: float
    upper_index: float  # Cpu or Ppu
    lower_index: float  # Cpl or Ppl
    mean: float
    sigma: float
    usl: float
    lsl: float
    sigma_kind: str  # "within" (Cp/Cpk) or "overall" (Pp/Ppk)
    warnings: list[str] = field(default_factory=list)


def _capability_from_sigma(
    mean: float, sigma: float, usl: float, lsl: float, sigma_kind: str, n: int | None
) -> CapabilityResult:
    """Shared math core. `n`, if given, triggers a small-sample warning per
    Overview 4.2 ("若过程失控、样本不足...UI 显示 warning，而不是给出无条件
    的绿色评分") - there is no dashboard yet (that's T4), so this layer emits
    the warning into the result instead, ready for T4 to surface.
    """
    warnings: list[str] = []
    if sigma <= 0:
        warnings.append("sigma is zero or negative - capability indices are undefined")
        nan = float("nan")
        return CapabilityResult(nan, nan, nan, nan, mean, sigma, usl, lsl, sigma_kind, warnings)

    cp = (usl - lsl) / (6 * sigma)
    cpu = (usl - mean) / (3 * sigma)
    cpl = (mean - lsl) / (3 * sigma)
    cpk = min(cpu, cpl)

    if n is not None and n < MIN_SAMPLE_SIZE:
        warnings.append(
            f"sample size n={n} is below the v1 minimum of {MIN_SAMPLE_SIZE} "
            "for a stable capability estimate"
        )

    return CapabilityResult(cp, cpk, cpu, cpl, mean, sigma, usl, lsl, sigma_kind, warnings)


def cp_cpk(
    mean: float, sigma_within: float, usl: float, lsl: float, n: int | None = None
) -> CapabilityResult:
    return _capability_from_sigma(mean, sigma_within, usl, lsl, "within", n)


def pp_ppk(
    mean: float, sigma_overall: float, usl: float, lsl: float, n: int | None = None
) -> CapabilityResult:
    return _capability_from_sigma(mean, sigma_overall, usl, lsl, "overall", n)


def sigma_within(x: list[float]) -> float:
    """Common-cause (within-subgroup) sigma estimate via moving range,
    consistent with imr.py's Phase I fit - this is the sigma Cp/Cpk use.
    """
    mr = moving_ranges(x)
    if not mr:
        raise ValueError("need at least 2 observations to estimate a moving-range sigma")
    return (sum(mr) / len(mr)) / D2_N2


def sigma_overall(x: list[float]) -> float:
    """Overall sample standard deviation - this is the sigma Pp/Ppk use."""
    if len(x) < 2:
        raise ValueError("need at least 2 observations to estimate an overall sample stdev")
    return statistics.stdev(x)
