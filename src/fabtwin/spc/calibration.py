"""Control-limit multipliers that account for a short Phase I.

Why: classical limits (I-MR +/- 3 sigma, EWMA L = 3, CUSUM h = 5 sigma) treat the Phase I
mean and sigma as if they were the true values. With 10-15 Phase I lots they are not, and
an underestimated sigma narrows every limit. Over 200 simulator seeds, a healthy chamber
monitored for 20 lots with a 10-lot Phase I showed at least one alarm 27 % of the time
(I-MR) and 21 % (EWMA), against about 5 % if the parameters were known (ADR 0003).

What this does: the charts here estimate location with the Phase I mean and scale with
the moving-range sigma (MRbar / d2). Both are location-scale equivariant, so for in-control
i.i.d. normal data the chart statistic, in units of the estimates, has a distribution that
depends only on the Phase I length n, the monitoring horizon h and the chart's own tuning
(lambda, k) - not on the process mean or sigma. A seeded Monte Carlo of that distribution
gives the multiplier for which the probability of **at least one false alarm in h Phase II
points** equals `target`. This is the unconditional (averaged over Phase I samples)
family-wise rate; a given Phase I can still be luckier or unluckier than average.

Assumptions, stated rather than hidden: in-control data are i.i.d. normal. That holds for
the simulator's per-lot means of etch_depth / etch_rate / cd_bias (sums of normal effects);
it does not hold for wiwnu (a range statistic) or defect_count (counts), where the
calibration is an approximation that should be checked by simulation before it is relied on.

PCA (T^2 / SPE) is not location-scale invariant in the same way (the retained subspace
depends on the correlation structure). `pca_multiplier` therefore uses a parametric
bootstrap from the Phase I correlation estimate - an approximation, recorded as such.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np

from fabtwin.spc.imr import D2_N2

DEFAULT_N_SIM = 20000
DEFAULT_SEED = 20261121


@dataclass(frozen=True)
class Calibration:
    """How a multiplier was obtained - stored in FrozenLimits.params for audit."""

    method: str
    multiplier: float
    target_false_alarm: float
    n_phase_i: int
    horizon: int
    n_sim: int
    seed: int
    note: str

    def as_params(self) -> dict:
        return asdict(self)


def _standardized_phase_ii(n: int, h: int, n_sim: int, seed: int) -> np.ndarray:
    """Phase II points in units of the Phase I estimates, for N(0, 1) data."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((n_sim, n + h))
    phase_i, phase_ii = x[:, :n], x[:, n:]
    mean = phase_i.mean(axis=1, keepdims=True)
    sigma = np.abs(np.diff(phase_i, axis=1)).mean(axis=1, keepdims=True) / D2_N2
    return (phase_ii - mean) / sigma


def _check(n: int, h: int, target: float) -> None:
    if n < 2:
        raise ValueError("Phase I needs at least 2 points")
    if h < 1:
        raise ValueError("horizon must be at least 1")
    if not 0 < target < 1:
        raise ValueError("target false-alarm probability must be in (0, 1)")


def _quantile(stat: np.ndarray, target: float) -> float:
    return float(np.quantile(stat, 1.0 - target))


def univariate_multiplier(
    method: Literal["I-MR", "EWMA", "CUSUM"],
    n_phase_i: int,
    horizon: int,
    target: float = 0.05,
    *,
    lam: float = 0.3,
    k_sigma: float = 0.5,
    n_sim: int = DEFAULT_N_SIM,
    seed: int = DEFAULT_SEED,
) -> Calibration:
    """Multiplier replacing I-MR's 3, EWMA's L or CUSUM's h (in sigma units)."""
    _check(n_phase_i, horizon, target)
    u = _standardized_phase_ii(n_phase_i, horizon, n_sim, seed)
    if method == "I-MR":
        stat = np.abs(u).max(axis=1)
        note = "max |x - mean| / sigma_hat over the horizon"
    elif method == "EWMA":
        if not 0 < lam <= 1:
            raise ValueError("lambda must be in (0, 1]")
        z = np.zeros(n_sim)
        peak = np.zeros(n_sim)
        for t in range(horizon):
            z = lam * u[:, t] + (1 - lam) * z
            peak = np.maximum(peak, np.abs(z))
        stat = peak / np.sqrt(lam / (2 - lam))
        note = f"EWMA lambda={lam}, asymptotic-width limits as in ewma.fit_phase_i"
    elif method == "CUSUM":
        s_hi = np.zeros(n_sim)
        s_lo = np.zeros(n_sim)
        peak = np.zeros(n_sim)
        for t in range(horizon):
            s_hi = np.maximum(0.0, s_hi + u[:, t] - k_sigma)
            s_lo = np.maximum(0.0, s_lo - u[:, t] - k_sigma)
            peak = np.maximum(peak, np.maximum(s_hi, s_lo))
        stat = peak
        note = f"two-sided CUSUM, k={k_sigma} sigma_hat"
    else:
        raise ValueError(f"unknown method {method!r}")
    return Calibration(
        method, _quantile(stat, target), target, n_phase_i, horizon, n_sim, seed, note
    )


def pca_multiplier(
    phase_i: np.ndarray,
    horizon: int,
    target: float = 0.05,
    *,
    statistic: Literal["T2", "SPE", "either"] = "either",
    alpha: float = 0.01,
    variance_threshold: float = 0.9,
    n_components: int | None = None,
    n_sim: int = 4000,
    seed: int = DEFAULT_SEED,
) -> Calibration:
    """Common factor c on the T^2 / SPE limit ratios so that P(any alarm in horizon) = target.

    Parametric bootstrap: Phase I and Phase II samples are drawn from a normal distribution
    with the Phase I correlation matrix, the PCA model is refitted on every simulated Phase I,
    and c is the (1 - target) quantile of the largest Phase II limit ratio. Approximation:
    it trusts the Phase I correlation estimate and normality.
    """
    from fabtwin.spc.pca_monitor import apply_phase_ii, fit_phase_i

    phase_i = np.asarray(phase_i, dtype=float)
    n, p = phase_i.shape
    _check(n, horizon, target)
    corr = np.corrcoef(phase_i, rowvar=False)
    chol = np.linalg.cholesky(corr + 1e-12 * np.eye(p))
    rng = np.random.default_rng(seed)
    peaks = np.empty(n_sim)
    for s in range(n_sim):
        x = rng.standard_normal((n + horizon, p)) @ chol.T
        model = fit_phase_i(
            x[:n], alpha=alpha, variance_threshold=variance_threshold, n_components=n_components
        )
        sc = apply_phase_ii(x[n:], model)
        t2r, sper = sc.t2 / model.t2_limit, sc.spe / model.spe_limit
        ratio = {"T2": t2r, "SPE": sper, "either": np.maximum(t2r, sper)}[statistic]
        peaks[s] = ratio.max()
    return Calibration(
        f"PCA-{statistic}",
        _quantile(peaks, target),
        target,
        n,
        horizon,
        n_sim,
        seed,
        "parametric bootstrap from the Phase I correlation matrix (approximation)",
    )
