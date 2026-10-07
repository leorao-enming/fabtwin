"""PCA / Hotelling T^2 / SPE: independent-reference and behavioural tests."""

from datetime import datetime, timedelta

import numpy as np
import pytest
from scipy import stats

from fabtwin.analysis import run_pca_monitor
from fabtwin.config import (
    FaultEvent,
    HierarchyConfig,
    RandomEffectConfig,
    RecipeConfig,
    SimulationConfig,
    ToolChamberConfig,
)
from fabtwin.detection import score_detection
from fabtwin.simulator import simulate
from fabtwin.spc import imr
from fabtwin.spc.pca_monitor import apply_phase_ii, fit_phase_i


def _healthy(n: int, seed: int) -> np.ndarray:
    """x2 tracks x1 closely (strong correlation); x3 independent."""
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    x2 = x1 + rng.normal(0, 0.15, n)
    x3 = rng.normal(0, 1, n)
    return np.column_stack([x1, x2, x3])


def test_eigenvalues_match_independent_covariance_decomposition():
    x = _healthy(200, 1)
    model = fit_phase_i(x, n_components=2)
    corr = np.corrcoef(x, rowvar=False)  # autoscaled covariance == correlation matrix
    expected = np.sort(np.linalg.eigvalsh(corr))[::-1]
    np.testing.assert_allclose(model.eigenvalues, expected, rtol=1e-9)
    assert model.eigenvalues.sum() == pytest.approx(3.0)  # trace of a 3x3 correlation matrix


def test_t2_limit_matches_published_f_value():
    # k=2, n=20, alpha=0.01: F_0.01(2,18) = 6.013 (standard F table)
    model = fit_phase_i(_healthy(20, 2), alpha=0.01, n_components=2)
    assert model.t2_limit == pytest.approx(2 * 21 * 19 / (20 * 18) * 6.013, rel=1e-3)


def test_spe_limit_reduces_to_chi_square_when_residual_eigenvalues_equal():
    # 4 variables = one common factor + equal independent noise -> after 1 PC the 3
    # residual eigenvalues are ~equal, so Box g*chi2(h) -> lambda * chi2_0.99(3) = lambda*11.345
    rng = np.random.default_rng(3)
    n = 20000
    lead = rng.normal(0, 3, n)
    x = np.column_stack([lead + rng.normal(0, 1, n) for _ in range(4)])
    model = fit_phase_i(x, n_components=1, alpha=0.01)
    lam = model.eigenvalues[1:]
    assert lam.max() / lam.min() < 1.1
    g, h = model.params["spe_box_g"], model.params["spe_box_h"]
    assert h == pytest.approx(3.0, rel=0.05)
    assert model.spe_limit == pytest.approx(g * stats.chi2.ppf(0.99, h))
    assert model.spe_limit == pytest.approx(lam.mean() * 11.345, rel=0.05)


def test_healthy_false_alarm_rate_close_to_alpha():
    model = fit_phase_i(_healthy(500, 4), alpha=0.01, n_components=2)
    scores = apply_phase_ii(_healthy(20000, 5), model)
    assert scores.t2_alarm.mean() == pytest.approx(0.01, abs=0.006)
    assert scores.spe_alarm.mean() < 0.03


def test_correlation_break_caught_by_spe_but_not_by_univariate_charts():
    """The reason this module exists: each marginal stays inside its limits."""
    phase_i = _healthy(300, 6)
    model = fit_phase_i(phase_i, alpha=0.01, n_components=2)
    rng = np.random.default_rng(7)
    n = 60
    # x2 decouples from x1 but keeps N(0,1)-like marginals, so univariate charts see nothing
    faulty = np.column_stack([rng.normal(0, 1, n) for _ in range(3)])
    scores = apply_phase_ii(faulty, model)
    assert scores.spe_alarm.mean() > 0.5

    for col in range(3):
        limits = imr.fit_phase_i(phase_i[:, col].tolist())
        pts = imr.apply_phase_ii(faulty[:, col].tolist(), limits)
        assert sum(p.out_of_control for p in pts) <= 2  # nominal false-alarm level only


def test_mean_shift_along_dominant_direction_caught_by_t2():
    model = fit_phase_i(_healthy(300, 8), alpha=0.01, n_components=2)
    # PC1 has sd ~ sqrt(1.95) ~ 1.4 in autoscaled units; a raw shift of 4.5 on x1 and x2
    # moves the score ~4.4 PC1 sd (T^2 ~ 19 vs limit ~9.4). A 2.5 shift (~2.4 sd) would
    # not be reliably caught at alpha=0.01 - that is what the limit means.
    shifted = _healthy(60, 9) + np.array([4.5, 4.5, 0.0])
    assert apply_phase_ii(shifted, model).t2_alarm.mean() > 0.8


def test_default_component_rule_keeps_residual_subspace():
    model = fit_phase_i(_healthy(200, 10), variance_threshold=0.99)
    assert 1 <= model.n_components <= 2
    assert model.params["cumulative_variance_retained"] <= 1.0


def test_input_validation():
    x = _healthy(50, 11)
    with pytest.raises(ValueError, match="at least 2"):
        fit_phase_i(x[:, :1])
    with pytest.raises(ValueError, match="constant"):
        fit_phase_i(np.column_stack([x[:, 0], np.ones(50)]))
    with pytest.raises(ValueError, match="residual subspace"):
        fit_phase_i(x, n_components=3)
    with pytest.raises(ValueError, match="more than"):
        fit_phase_i(x[:2], n_components=2)
    with pytest.raises(ValueError, match="alpha"):
        fit_phase_i(x, alpha=1.5)
    model = fit_phase_i(x, n_components=1)
    with pytest.raises(ValueError, match="matching"):
        apply_phase_ii(x[:, :2], model)


def test_model_is_frozen():
    model = fit_phase_i(_healthy(50, 12), n_components=1)
    with pytest.raises(AttributeError):
        model.t2_limit = 1e9  # type: ignore[misc]


START = datetime(2026, 1, 1)


def _sim(fault: FaultEvent | None) -> SimulationConfig:
    return SimulationConfig(
        seed=11,
        start_time=START,
        recipe=RecipeConfig(
            recipe_id="R1", rf_power_w=200, pressure_mtorr=50, gas_flow_sccm=50, etch_time_s=60
        ),
        tool_chambers=[
            ToolChamberConfig(tool_id="T1", chamber_id="CH-A"),
            ToolChamberConfig(tool_id="T1", chamber_id="CH-B"),
        ],
        hierarchy=HierarchyConfig(
            lot_size_wafers=10, sites_per_wafer=5, n_lots=40, lot_interval_minutes=60
        ),
        random_effects=RandomEffectConfig(
            lot_sigma_nm=0.5, wafer_sigma_nm=0.5, site_noise_sigma_nm=0.5
        ),
        faults=[fault] if fault else [],
    )


def test_pca_run_through_simulator_and_detection_scoring():
    fault = FaultEvent(
        event_id="SHIFT-1",
        fault_type="step_mean_shift",
        onset=START + timedelta(hours=15),
        tool_id="T1",
        chamber_id="CH-A",
        metric="etch_depth",
        magnitude=8.0,
    )
    obs = simulate(_sim(fault)).observations
    metrics = ["etch_depth", "cd_bias", "wiwnu"]
    hit = run_pca_monitor(obs, "T1", "CH-A", metrics, phase_i_n_lots=15, n_components=2)
    sibling = run_pca_monitor(obs, "T1", "CH-B", metrics, phase_i_n_lots=15, n_components=2)
    assert hit.method == "PCA-T2-SPE"
    assert hit.limits.params["metrics"] == metrics
    score = score_detection(hit, fault)
    assert score.event_detected and score.pre_fault_false_alarms == 0
    assert not sibling.any_out_of_control


def test_run_pca_monitor_rejects_single_metric():
    obs = simulate(_sim(None)).observations
    with pytest.raises(ValueError, match="at least 2"):
        run_pca_monitor(obs, "T1", "CH-A", ["etch_depth"], 15)
