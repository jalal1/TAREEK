# SPDX-License-Identifier: GPL-3.0-or-later
"""
Mode types and configuration for multi-modal transportation.

This module is the single source of truth for canonical transportation modes.
All surveys and plan generators should import mode constants from here.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Any


# ── Canonical transport modes (single source of truth) ──────────────────────
# All surveys must map their raw mode labels to these values.
MODE_CAR = 'Car'
MODE_BUS = 'Bus'
MODE_RAIL = 'Rail'
MODE_WALK = 'Walk'
MODE_BIKE = 'Bike'
MODE_SCHOOL_BUS = 'School Bus'
MODE_RIDESHARE = 'Rideshare'
MODE_OTHER = 'Other'
# A car passenger (NHTS DRVR_FLG 2, TBI driver "Passenger"). ``Car`` is the
# driver. A passenger trip puts no extra vehicle on the road.
MODE_RIDE = 'Ride'

CANONICAL_MODES = {
    MODE_CAR, MODE_BUS, MODE_RAIL, MODE_WALK,
    MODE_BIKE, MODE_SCHOOL_BUS, MODE_RIDESHARE, MODE_OTHER, MODE_RIDE,
}

# Driver share of car trips (driver + passenger) per destination purpose.
# NHTS 2022, weekday travel days in the regular months (Mar-May, Sep-Nov),
# trip-weighted (WTTRDFIN), after the pipeline's NHTS cleaning. Used only
# for a survey source that has no driver field (for example ``bham_local``):
# its ``Car`` share is split into Car (driver) and Ride (passenger) with
# these values. TBI 2023 gives nearly the same values (all 0.78, Work 0.95,
# School 0.31).
NHTS_2022_DRIVER_SHARE = {
    'Home': 0.773,
    'Work': 0.952,
    'School': 0.302,
    'Shopping': 0.799,
    'Social': 0.695,
    'Dining': 0.727,
    'Other': 0.747,
    'all': 0.771,
}

# Modes that every run has unless the config switches them off
# (``modes.<name>.enabled: false``). Both are teleported in MATSim, so they
# put no vehicle on the network: ``ride`` is the car passenger, ``school_bus``
# the school bus (no GTFS feed has school buses).
DEFAULT_EXTRA_MODES = {
    'ride': {
        'enabled': True,
        'matsim_mode': 'ride',
        'availability': 'universal',
        'survey_rate': 'auto',
    },
    'school_bus': {
        'enabled': True,
        'matsim_mode': 'school_bus',
        'availability': 'universal',
        'survey_rate': 'auto',
    },
}


def effective_modes_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """The config ``modes`` section plus the default extra modes.

    A config entry for ``ride`` or ``school_bus`` is merged over the default,
    so ``{"ride": {"enabled": false}}`` switches the mode off. Returns a new
    dict; the config is not changed.
    """
    modes = dict(config.get('modes') or {})
    for name, default in DEFAULT_EXTRA_MODES.items():
        user = modes.get(name)
        merged = dict(default)
        if isinstance(user, dict):
            merged.update(user)
        modes[name] = merged
    return modes


def is_mode_enabled(config: Dict[str, Any], name: str) -> bool:
    """True if mode ``name`` is enabled after the defaults are applied."""
    cfg = effective_modes_config(config).get(name)
    return isinstance(cfg, dict) and bool(cfg.get('enabled', True))


class ModeType(Enum):
    """Canonical transportation modes as enum."""
    CAR = "car"
    BUS = "bus"
    RAIL = "rail"
    WALK = "walk"
    BIKE = "bike"
    SCHOOL_BUS = "school_bus"
    RIDESHARE = "rideshare"
    OTHER = "other"
    RIDE = "ride"

    @classmethod
    def from_survey_mode(cls, survey_mode: str) -> 'ModeType':
        """
        Map survey canonical mode string (e.g., 'Car', 'Bus') to ModeType enum.

        Args:
            survey_mode: Mode string from survey data (uses MODE_* constants)

        Returns:
            Corresponding ModeType enum value
        """
        mapping = {
            MODE_CAR: cls.CAR,
            MODE_BUS: cls.BUS,
            MODE_RAIL: cls.RAIL,
            MODE_WALK: cls.WALK,
            MODE_BIKE: cls.BIKE,
            MODE_SCHOOL_BUS: cls.SCHOOL_BUS,
            MODE_RIDESHARE: cls.RIDESHARE,
            MODE_OTHER: cls.OTHER,
            MODE_RIDE: cls.RIDE,
        }
        return mapping.get(survey_mode, cls.OTHER)

    def to_output_mode(self, output_format: str = 'matsim') -> str:
        """
        Convert to output format mode string.

        Args:
            output_format: Target output format ('matsim', 'sumo', etc.)

        Returns:
            Mode string appropriate for the output format
        """
        if output_format == 'matsim':
            # MATSim uses 'pt' for public transit modes
            matsim_mapping = {
                ModeType.CAR: 'car',
                ModeType.BUS: 'pt',
                ModeType.RAIL: 'pt',
                ModeType.WALK: 'walk',
                ModeType.BIKE: 'bike',
                # Teleported: school buses are not in the GTFS feeds.
                ModeType.SCHOOL_BUS: 'school_bus',
                ModeType.RIDESHARE: 'car',
                ModeType.OTHER: 'car',
                # Car passenger, teleported (no vehicle on the network).
                ModeType.RIDE: 'ride',
            }
            return matsim_mapping.get(self, 'car')
        # Default: return enum value
        return self.value

    def is_transit(self) -> bool:
        """Check if this is a public transit mode."""
        return self in {ModeType.BUS, ModeType.RAIL}


@dataclass
class ModeConfig:
    """Configuration for a single mode, loaded from config.json.

    Rate configuration fields (for Phase 2 mode choice):
    - survey_rate: "auto" to compute from survey, or float value (0.0-1.0)
    - config_rate: Target rate override, or None to skip blending
    - blend_weight: How to blend survey vs config (0.0=survey only, 1.0=config only)
    - share_adjustment: Additive adjustment to final rate (e.g., +0.05 = +5 points)
    """
    mode_type: ModeType
    matsim_mode: str              # Output mode string for MATSim (e.g., "pt")
    availability_type: str        # "universal", "gtfs", "distance", "zone_list"
    availability_params: Dict[str, Any]  # Type-specific parameters
    enabled: bool                 # Whether this mode is active (default True)

    # Rate configuration (Phase 2)
    survey_rate: str | float      # "auto" or fixed float value
    config_rate: Optional[float]  # Target rate for blending, None = no override
    blend_weight: float           # 0.0 = pure survey, 1.0 = pure config
    share_adjustment: float       # Additive adjustment after blending

    @classmethod
    def from_config(cls, mode_name: str, config: Dict[str, Any]) -> 'ModeConfig':
        """
        Create ModeConfig from config.json entry.

        Args:
            mode_name: Mode name key (e.g., "car", "bus")
            config: Mode configuration dict from config.json

        Returns:
            ModeConfig instance
        """
        # Parse mode type from name
        try:
            mode_type = ModeType(mode_name.lower())
        except ValueError:
            mode_type = ModeType.OTHER

        # Parse availability
        availability = config.get('availability', 'universal')
        if isinstance(availability, str):
            availability_type = availability
            availability_params = {}
        else:
            availability_type = availability.get('type', 'universal')
            availability_params = {k: v for k, v in availability.items() if k != 'type'}

        # Parse rate configuration (with defaults for backwards compatibility)
        survey_rate = config.get('survey_rate', 'auto')
        config_rate = config.get('config_rate', None)
        blend_weight = config.get('blend_weight', 0.0)
        share_adjustment = config.get('share_adjustment', 0.0)

        return cls(
            mode_type=mode_type,
            matsim_mode=config.get('matsim_mode', mode_type.to_output_mode('matsim')),
            availability_type=availability_type,
            availability_params=availability_params,
            enabled=config.get('enabled', True),
            survey_rate=survey_rate,
            config_rate=config_rate,
            blend_weight=blend_weight,
            share_adjustment=share_adjustment,
        )


def get_default_car_config() -> Dict[str, Any]:
    """Return default car mode configuration."""
    return {
        "car": {
            "matsim_mode": "car",
            "availability": "universal"
        }
    }
