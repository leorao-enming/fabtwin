"""Multivariate monitoring: PCA with Hotelling T^2 and SPE (Q) - Overview 4.2.

Univariate charts watch each variable alone, so they miss faults that break
the *correlation* between variables while every marginal stays inside its
limits. A PCA model fitted on a healthy Phase I window splits each new
observation into the retained-component subspace (monitored by T^2) and the
residual subspace (monitored by SPE).

Limits (both frozen at fit time and recorded in `params`):
- T^2 for future observations: k(n+1)(n-1) / (n(n-k)) * F_alpha(k, n-k)
  (Phase II / future-observation form; n = Phase I sample size).
- SPE: Box's weighted chi-square approximation g * chi2_alpha(h) with
  g = theta2/theta1, h = theta1^2/theta2, theta_i = sum of the i-th powers of
  the discarded eigenvalues.

When to use which: one metric over time -> I-MR/EWMA/CUSUM. Several correlated
sensors/metrics at the same instant -> this module. Mixing them without saying
so is the mistake Overview 4.2 warns about.

Scaling uses Phase I mean/std (autoscaling), so variables in different units
are comparable. A constant Phase I column cannot be scaled and is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class PCAMonitorModel:
    mean: np.ndarray
    scale: np.ndarray
    loadings: np.ndarray  # (p, k)
    eigenvalues: np.ndarray  # all p, descending
    n_components: int
    n_phase_i: int
    alpha: float
    t2_limit: float
    spe_limit: float
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PCAScores:
    t2: np.ndarray
    spe: np.ndarray
    t2_alarm: np.ndarray
    spe_alarm: np.ndarray

    @property
    def alarm(self) -> np.ndarray:
        return self.t2_alarm | self.spe_alarm


def fit_phase_i(
    x: np.ndarray,
    alpha: float = 0.01,
    variance_threshold: float = 0.9,
    n_components: int | None = None,
) -> PCAMonitorModel:
    """`n_components` overrides the cumulative-variance rule when given."""
    x = np.asarray(x, dtype=float)
    if x.ndim != 2:
        raise ValueError("x must be a 2-D (observations x variables) array")
    n, p = x.shape
    if p < 2:
        raise ValueError("multivariate monitoring needs at least 2 variables")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    if not 0 < variance_threshold <= 1:
        raise ValueError("variance_threshold must be in (0, 1]")

    mean = x.mean(axis=0)
    scale = x.std(axis=0, ddof=1)
    if np.any(scale == 0):
        raise ValueError("a Phase I variable is constant and cannot be scaled")
    z = (x - mean) / scale

    eigvals, eigvecs = np.linalg.eigh(np.cov(z, rowvar=False))
    order = np.argsort(eigvals)[::-1]
    eigvals = np.clip(eigvals[order], 0.0, None)
    eigvecs = eigvecs[:, order]

    if n_components is None:
        cum = np.cumsum(eigvals) / eigvals.sum()
        k = int(np.searchsorted(cum, variance_threshold - 1e-12) + 1)
        k = min(k, p - 1)
    else:
        k = n_components
    if not 1 <= k <= p - 1:
        raise ValueError(f"n_components must be in [1, {p - 1}] so a residual subspace remains")
    if n <= k + 1:
        raise ValueError(f"Phase I needs more than k+1={k + 1} observations, got {n}")

    residual = eigvals[k:]
    theta1, theta2 = float(residual.sum()), float((residual**2).sum())
    if theta1 <= 0 or theta2 <= 0:
        raise ValueError("residual subspace has no variance; SPE limit is undefined")
    g, h = theta2 / theta1, theta1**2 / theta2

    t2_limit = k * (n + 1) * (n - 1) / (n * (n - k)) * float(stats.f.ppf(1 - alpha, k, n - k))
    spe_limit = g * float(stats.chi2.ppf(1 - alpha, h))

    return PCAMonitorModel(
        mean=mean,
        scale=scale,
        loadings=eigvecs[:, :k],
        eigenvalues=eigvals,
        n_components=k,
        n_phase_i=n,
        alpha=alpha,
        t2_limit=t2_limit,
        spe_limit=spe_limit,
        params={
            "alpha": alpha,
            "variance_threshold": variance_threshold,
            "n_components": k,
            "n_phase_i": n,
            "cumulative_variance_retained": float(eigvals[:k].sum() / eigvals.sum()),
            "spe_box_g": g,
            "spe_box_h": h,
            "t2_limit": t2_limit,
            "spe_limit": spe_limit,
        },
    )


def apply_phase_ii(x: np.ndarray, model: PCAMonitorModel) -> PCAScores:
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or x.shape[1] != model.mean.shape[0]:
        raise ValueError("x must be (observations x variables) matching the fitted model")
    z = (x - model.mean) / model.scale
    t = z @ model.loadings
    t2 = np.sum(t**2 / model.eigenvalues[: model.n_components], axis=1)
    resid = z - t @ model.loadings.T
    spe = np.sum(resid**2, axis=1)
    return PCAScores(t2=t2, spe=spe, t2_alarm=t2 > model.t2_limit, spe_alarm=spe > model.spe_limit)
