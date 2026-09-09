"""The random-effect decomposition from docs/data-dictionary.md section 5.

Five layers, kept explicitly separate per the data dictionary:

1. fixed recipe effect       -> fixed_effect_etch_depth_nm / fixed_effect_cd_bias_nm
2. tool/chamber random effect -> draw_tool_chamber_offsets
3. lot/wafer effect           -> draw_lot_effect / draw_wafer_effect
4. time-dependent drift/fault -> handled in faults.py, not here
5. measurement noise          -> measurement_noise

All randomness in this module goes through a single numpy Generator passed
in by the caller (simulator.py), never a module-level RNG, so a run is
reproducible end to end from one seed.

The fixed-effect formulas below are deliberately synthetic calibration
constants, not derived from real plasma-etch physics - this is a synthetic
process per the Overview and README. They only need to be directionally
plausible (more RF power / time -> deeper etch) and internally consistent
run to run.
"""

from __future__ import annotations

import numpy as np

from fabtwin.config import RecipeConfig, ToolChamberConfig

# Synthetic calibration constants - see module docstring.
_ETCH_RATE_K = 40.0  # nm/min per (W / mTorr) at gas_flow_sccm=100
_CD_BASE_NM = 0.0
_CD_POWER_COEF_NM_PER_W = 0.02
_CD_PRESSURE_COEF_NM_PER_MTORR = -0.05
_REFERENCE_RF_POWER_W = 200.0
_REFERENCE_PRESSURE_MTORR = 50.0


def fixed_effect_etch_rate_nm_per_min(recipe: RecipeConfig) -> float:
    return _ETCH_RATE_K * recipe.rf_power_w / recipe.pressure_mtorr * (recipe.gas_flow_sccm / 100.0)


def fixed_effect_etch_depth_nm(recipe: RecipeConfig) -> float:
    rate = fixed_effect_etch_rate_nm_per_min(recipe)
    return rate * (recipe.etch_time_s / 60.0)


def fixed_effect_cd_bias_nm(recipe: RecipeConfig) -> float:
    return (
        _CD_BASE_NM
        + _CD_POWER_COEF_NM_PER_W * (recipe.rf_power_w - _REFERENCE_RF_POWER_W)
        + _CD_PRESSURE_COEF_NM_PER_MTORR * (recipe.pressure_mtorr - _REFERENCE_PRESSURE_MTORR)
    )


def draw_tool_chamber_offsets(
    tool_chambers: list[ToolChamberConfig], rng: np.random.Generator
) -> dict[tuple[str, str], tuple[float, float]]:
    """Draw one (depth_offset_nm, cd_bias_offset_nm) pair per chamber, once.

    Held fixed for the entire simulation run - this is what makes two
    chambers on the same tool comparable-but-different (case 2, tool/chamber
    comparison) rather than statistically identical.
    """
    offsets: dict[tuple[str, str], tuple[float, float]] = {}
    for tc in tool_chambers:
        depth_offset = rng.normal(0.0, tc.depth_offset_sigma_nm)
        cd_offset = rng.normal(0.0, tc.cd_bias_offset_sigma_nm)
        offsets[(tc.tool_id, tc.chamber_id)] = (float(depth_offset), float(cd_offset))
    return offsets


def draw_lot_effect(rng: np.random.Generator, sigma_nm: float) -> float:
    return float(rng.normal(0.0, sigma_nm)) if sigma_nm > 0 else 0.0


def draw_wafer_effect(rng: np.random.Generator, sigma_nm: float) -> float:
    return float(rng.normal(0.0, sigma_nm)) if sigma_nm > 0 else 0.0


def measurement_noise(rng: np.random.Generator, sigma_nm: float) -> float:
    return float(rng.normal(0.0, sigma_nm)) if sigma_nm > 0 else 0.0
