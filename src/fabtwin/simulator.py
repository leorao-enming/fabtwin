"""Orchestrates one full simulation run: config -> observation table.

Implements the hierarchy from docs/data-dictionary.md section 1
(tool -> chamber -> lot -> wafer -> site) and produces the long-format
observation table from section 4, keeping the hidden-truth decomposition
(section 5) in a separate structure that analysis code never sees -
SimulationResult.observations is the only thing SPC/capability/dashboard
code (T2+) is allowed to read; .hidden_truth exists for validation/tests.

Within one lot, all wafers/sites share a single processing timestamp (the
lot's timestamp) - a v1 simplification; nothing in the data dictionary
requires finer-grained intra-lot timing yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from fabtwin.config import METRIC_UNITS, SimulationConfig
from fabtwin.effects import (
    draw_lot_effect,
    draw_tool_chamber_offsets,
    draw_wafer_effect,
    fixed_effect_cd_bias_nm,
    fixed_effect_etch_depth_nm,
    measurement_noise,
)
from fabtwin.faults import (
    noise_sigma_multiplier,
    sensor_bias_offset,
    total_process_contribution,
)
from fabtwin.metrics import (
    defect_count_for_wafer,
    etch_rate_from_depth,
    wiwnu_from_site_depths,
)

# Site pattern: center + N/E/S/W, per docs/data-dictionary.md section 1.
SITE_IDS: tuple[str, ...] = ("center", "N", "E", "S", "W")

OBSERVATION_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "tool_id",
    "chamber_id",
    "lot_id",
    "wafer_id",
    "site_id",
    "recipe_id",
    "metric",
    "value",
    "unit",
)


@dataclass
class SimulationResult:
    observations: pd.DataFrame
    hidden_truth: dict[str, Any]


def simulate(config: SimulationConfig) -> SimulationResult:
    if config.hierarchy.sites_per_wafer > len(SITE_IDS):
        raise ValueError(
            f"sites_per_wafer={config.hierarchy.sites_per_wafer} exceeds the v1 site "
            f"pattern of {len(SITE_IDS)} points ({SITE_IDS}) - see data-dictionary.md section 9."
        )
    site_ids = SITE_IDS[: config.hierarchy.sites_per_wafer]

    rng = np.random.default_rng(config.seed)
    tc_offsets = draw_tool_chamber_offsets(config.tool_chambers, rng)
    fixed_depth = fixed_effect_etch_depth_nm(config.recipe)
    fixed_cd_bias = fixed_effect_cd_bias_nm(config.recipe)

    rows: list[dict[str, Any]] = []

    for tc in config.tool_chambers:
        depth_offset, cd_offset = tc_offsets[(tc.tool_id, tc.chamber_id)]
        t = config.start_time

        for lot_index in range(config.hierarchy.n_lots):
            lot_id = f"LOT-{tc.tool_id}-{tc.chamber_id}-{lot_index:04d}"
            lot_depth_effect = draw_lot_effect(rng, config.random_effects.lot_sigma_nm)
            lot_cd_effect = draw_lot_effect(rng, config.random_effects.cd_bias_lot_sigma_nm)

            depth_process_shift = total_process_contribution(
                config.faults, tc.tool_id, tc.chamber_id, "etch_depth", t
            )
            cd_process_shift = total_process_contribution(
                config.faults, tc.tool_id, tc.chamber_id, "cd_bias", t
            )
            depth_sigma_mult = noise_sigma_multiplier(
                config.faults, tc.tool_id, tc.chamber_id, "etch_depth", t
            )
            cd_sigma_mult = noise_sigma_multiplier(
                config.faults, tc.tool_id, tc.chamber_id, "cd_bias", t
            )
            depth_sensor_bias = sensor_bias_offset(
                config.faults, tc.tool_id, tc.chamber_id, "etch_depth", t
            )
            cd_sensor_bias = sensor_bias_offset(
                config.faults, tc.tool_id, tc.chamber_id, "cd_bias", t
            )

            for wafer_index in range(config.hierarchy.lot_size_wafers):
                wafer_id = f"{lot_id}-W{wafer_index:03d}"
                wafer_depth_effect = draw_wafer_effect(rng, config.random_effects.wafer_sigma_nm)
                wafer_cd_effect = draw_wafer_effect(
                    rng, config.random_effects.cd_bias_wafer_sigma_nm
                )

                site_depths: list[float] = []
                common = {
                    "timestamp": t.isoformat(),
                    "tool_id": tc.tool_id,
                    "chamber_id": tc.chamber_id,
                    "lot_id": lot_id,
                    "wafer_id": wafer_id,
                    "recipe_id": config.recipe.recipe_id,
                }

                for site_id in site_ids:
                    depth_noise = measurement_noise(
                        rng, config.random_effects.site_noise_sigma_nm * depth_sigma_mult
                    )
                    etch_depth = (
                        fixed_depth
                        + depth_offset
                        + lot_depth_effect
                        + wafer_depth_effect
                        + depth_process_shift
                        + depth_noise
                        + depth_sensor_bias
                    )
                    site_depths.append(etch_depth)

                    cd_noise = measurement_noise(
                        rng, config.random_effects.cd_bias_noise_sigma_nm * cd_sigma_mult
                    )
                    cd_bias = (
                        fixed_cd_bias
                        + cd_offset
                        + lot_cd_effect
                        + wafer_cd_effect
                        + cd_process_shift
                        + cd_noise
                        + cd_sensor_bias
                    )

                    etch_rate = etch_rate_from_depth(etch_depth, config.recipe.etch_time_s)

                    rows.append(
                        {
                            **common,
                            "site_id": site_id,
                            "metric": "etch_depth",
                            "value": etch_depth,
                            "unit": METRIC_UNITS["etch_depth"],
                        }
                    )
                    rows.append(
                        {
                            **common,
                            "site_id": site_id,
                            "metric": "etch_rate",
                            "value": etch_rate,
                            "unit": METRIC_UNITS["etch_rate"],
                        }
                    )
                    rows.append(
                        {
                            **common,
                            "site_id": site_id,
                            "metric": "cd_bias",
                            "value": cd_bias,
                            "unit": METRIC_UNITS["cd_bias"],
                        }
                    )

                wiwnu = wiwnu_from_site_depths(site_depths)
                defect_count = defect_count_for_wafer(
                    rng,
                    base_rate=config.random_effects.defect_count_base_rate,
                    fault_delta=total_process_contribution(
                        config.faults, tc.tool_id, tc.chamber_id, "defect_count", t
                    ),
                    variance_multiplier=noise_sigma_multiplier(
                        config.faults, tc.tool_id, tc.chamber_id, "defect_count", t
                    ),
                    sensor_bias=sensor_bias_offset(
                        config.faults, tc.tool_id, tc.chamber_id, "defect_count", t
                    ),
                )
                rows.append(
                    {
                        **common,
                        "site_id": None,
                        "metric": "wiwnu",
                        "value": wiwnu,
                        "unit": METRIC_UNITS["wiwnu"],
                    }
                )
                rows.append(
                    {
                        **common,
                        "site_id": None,
                        "metric": "defect_count",
                        "value": float(defect_count),
                        "unit": METRIC_UNITS["defect_count"],
                    }
                )

            t = t + timedelta(minutes=config.hierarchy.lot_interval_minutes)

    observations = pd.DataFrame(rows, columns=list(OBSERVATION_COLUMNS))
    hidden_truth: dict[str, Any] = {
        "tool_chamber_offsets": tc_offsets,
        "fixed_effect_etch_depth_nm": fixed_depth,
        "fixed_effect_cd_bias_nm": fixed_cd_bias,
        "faults": [f.model_dump() for f in config.faults],
    }
    return SimulationResult(observations=observations, hidden_truth=hidden_truth)
