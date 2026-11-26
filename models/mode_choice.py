# SPDX-License-Identifier: GPL-3.0-or-later
"""
Mode choice model for multi-modal transportation.

This module provides the ModeChoiceModel class which selects transportation
modes for trips based on survey rates and availability constraints.

Phase 2 Implementation:
- Computes mode shares from survey data (blended across multiple surveys)
- Applies config rate blending and share adjustments
- Filters to available modes and renormalizes
- Samples mode from final distribution
- Supports chain consistency (entire chain uses same mode)
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Set

import numpy as np
import pandas as pd

from models.mode_types import (ModeType, ModeConfig, get_default_car_config, MODE_CAR,
                               MODE_RIDE, NHTS_2022_DRIVER_SHARE, effective_modes_config)
from models.mode_availability import ModeAvailabilityManager, Location, haversine_meters

logger = logging.getLogger(__name__)


@dataclass
class Leg:
    """Represents travel between two activities."""
    mode: str  # Output format mode string (e.g., "car", "pt")


class ModeChoiceModel:
    """
    Selects transportation mode for each trip based on survey rates.

    The mode choice process:
    1. Get available modes for the OD pair (from availability_manager)
    2. Get survey rates for the trip purpose (blended across surveys)
    3. Apply config rate blending and share adjustments per mode
    4. Filter to available modes only
    5. Renormalize so probabilities sum to 1.0
    6. Sample mode from the distribution

    For chain consistency, the entire activity chain uses the same mode,
    with retry logic if the chosen mode isn't available for all legs.
    """

    def __init__(self, config: Dict[str, Any],
                 availability_manager: Optional[ModeAvailabilityManager] = None,
                 survey_data: Optional[Dict[str, pd.DataFrame]] = None,
                 survey_weights: Optional[Dict[str, float]] = None,
                 gtfs_avail_manager=None):
        """
        Initialize mode choice model.

        Args:
            config: Full configuration dict (expects 'modes' and 'mode_choice' sections)
            availability_manager: Optional availability manager. If None, one will be created.
            survey_data: Optional dict of {survey_name: DataFrame} with survey trip data.
                        Each DataFrame should have 'mode_type' and 'destination_purpose' columns.
            survey_weights: Optional dict of {survey_name: weight} for blending surveys.
                           If None, equal weights are used.
            gtfs_avail_manager: Optional GTFSAvailabilityManager for transit availability.
                               Passed through to ModeAvailabilityManager if creating one.
        """
        self.config = config

        # Get modes config, default to car if not present
        if not config.get('modes'):
            logger.warning("No 'modes' section in config, defaulting to car-only mode "
                           "(plus the default ride and school_bus modes)")
            config = {**config, 'modes': get_default_car_config()}
        # The config modes plus ride (car passenger) and school_bus, which are
        # on unless the config switches them off (models.mode_types).
        modes_config = effective_modes_config(config)

        # Parse mode configurations
        self.mode_configs: Dict[ModeType, ModeConfig] = {}
        for mode_name, mode_cfg in modes_config.items():
            if not isinstance(mode_cfg, dict):
                continue
            if not mode_cfg.get('enabled', True):
                continue
            mc = ModeConfig.from_config(mode_name, mode_cfg)
            self.mode_configs[mc.mode_type] = mc

        # Ensure car mode is always available
        if ModeType.CAR not in self.mode_configs:
            logger.warning("Car mode not in config, adding default car mode")
            car_cfg = get_default_car_config()['car']
            self.mode_configs[ModeType.CAR] = ModeConfig.from_config('car', car_cfg)

        # Initialize or use provided availability manager
        if availability_manager is not None:
            self.availability_manager = availability_manager
        else:
            self.availability_manager = ModeAvailabilityManager(
                modes_config, gtfs_avail_manager=gtfs_avail_manager
            )

        # Mode choice parameters
        mode_choice_config = config.get('mode_choice', {})
        self.fallback_mode = ModeType(mode_choice_config.get('fallback_mode', 'car'))
        self.chain_consistency = mode_choice_config.get('chain_consistency', True)
        self.min_samples_per_purpose = mode_choice_config.get('min_samples_per_purpose', 30)
        self.max_chain_mode_retries = mode_choice_config.get('max_chain_mode_retries', 5)
        # Mode shares from trip-weighted survey trips (default). False = the
        # old trip count, which over-represents the groups that report more
        # trips (NHTS School car share: 54.6% weighted, 65.5% unweighted).
        self.weighted_shares = bool(mode_choice_config.get('weighted_shares', True))
        # Short legs (e.g. Work->Lunch) get a walk pass-through: they don't
        # constrain the chain intersection, and emit as walk regardless of the
        # chain's primary mode. Only applies to interior legs (neither
        # endpoint is Home). 0 disables. Default 800m matches the typical
        # 10-minute-walk definition used in urban planning.
        self.walk_passthrough_max_meters = float(
            mode_choice_config.get('walk_passthrough_max_meters', 200.0)
        )

        # Default random stream. Plan generators replace it at the start of
        # each OD pair (utils.rng.reseed), so the modes do not depend on the
        # worker schedule. Never use an unseeded default_rng() here: it takes
        # fresh OS entropy and makes plan generation unrepeatable (P7).
        from utils.rng import derive_seed
        base_seed = config.get('plan_generation', {}).get('random_seed', 42)
        self.rng = np.random.default_rng(derive_seed(base_seed, 'mode_choice'))

        # Store survey data for rate computation
        self.survey_data = survey_data
        self.survey_weights = survey_weights

        # Compute survey rates (mode shares per purpose)
        self.survey_rates: Dict[str, Dict[ModeType, float]] = {}
        if survey_data:
            self._compute_survey_rates()
        else:
            logger.warning("No survey data provided - mode choice will use fallback mode")

        # Statistics for logging
        self.stats = {
            'mode_samples': {mt: 0 for mt in ModeType},
            'fallback_used': 0,
            'chain_retries': 0,
            'purposes_with_fallback': set(),
            'chain_mode_selections': {},  # {(mode, purpose, num_legs): count}
            'chain_availability': {},     # {frozenset(modes): count}

            # --- Chain-consistency diagnostics ---
            # Per-mode count of legs where the mode was available on that leg.
            # Compared against `mode_eligible_after_intersection` to quantify
            # how much each mode is being filtered out by chain consistency.
            'mode_eligible_per_leg': {mt: 0 for mt in ModeType},
            # Per-mode count of chains where the mode survived the intersection.
            # Multiplied by chain length to make it leg-comparable.
            'mode_eligible_after_intersection': {mt: 0 for mt in ModeType},
            # Per-mode count of chains where the mode was eligible on EVERY
            # leg individually but was knocked out by walk-pass-through being
            # disabled would have helped. Tracks the chain-consistency leak.
            'mode_lost_to_chain_consistency': {mt: 0 for mt in ModeType},
            # Distribution of chain lengths actually seen.
            'chain_length_counts': {},  # {num_legs: count}
            # Walk-pass-through usage.
            'walk_passthrough_legs': 0,
            'walk_passthrough_chains': 0,
            # Retry telemetry.
            'chain_retry_attempts': 0,
            'chain_retry_succeeded': 0,
            'chain_retry_exhausted': 0,
        }

        logger.info(f"ModeChoiceModel initialized with {len(self.mode_configs)} modes: "
                    f"{[m.value for m in self.mode_configs.keys()]}")

    def _compute_survey_rates(self) -> None:
        """
        Compute mode shares from survey data, blended across multiple surveys.

        Computes rates per destination_purpose and overall ('all').
        Uses survey weights for blending when multiple surveys are provided.

        Results stored in self.survey_rates: {purpose: {ModeType: share}}
        """
        if not self.survey_data:
            logger.warning("No survey data available for rate computation")
            return

        logger.info("Computing mode shares from survey data...")

        # Normalize survey weights
        if self.survey_weights:
            total_weight = sum(self.survey_weights.values())
            normalized_weights = {k: v / total_weight for k, v in self.survey_weights.items()}
        else:
            # Equal weights if not specified
            n_surveys = len(self.survey_data)
            normalized_weights = {name: 1.0 / n_surveys for name in self.survey_data}

        logger.debug(f"  Survey weights (normalized): {normalized_weights}")

        # Get all unique purposes across all surveys
        all_purposes = set()
        for df in self.survey_data.values():
            if 'destination_purpose' in df.columns:
                all_purposes.update(df['destination_purpose'].dropna().unique())

        purposes_to_compute = list(all_purposes) + ['all']
        logger.debug(f"  Computing rates for purposes: {purposes_to_compute}")

        # Compute rates per purpose
        for purpose in purposes_to_compute:
            blended_rates: Dict[ModeType, float] = {}

            for survey_name, df in self.survey_data.items():
                weight = normalized_weights.get(survey_name, 0.0)
                if weight == 0:
                    continue

                # Filter by purpose (or use all trips for 'all')
                if purpose == 'all':
                    purpose_df = df
                else:
                    purpose_df = df[df['destination_purpose'] == purpose]

                if len(purpose_df) < self.min_samples_per_purpose:
                    logger.debug(f"  Survey '{survey_name}' has only {len(purpose_df)} trips for "
                                f"purpose '{purpose}' (min: {self.min_samples_per_purpose})")
                    continue

                # Compute mode shares for this survey
                if 'mode_type' not in purpose_df.columns:
                    logger.warning(f"  Survey '{survey_name}' missing 'mode_type' column")
                    continue

                mode_counts = self._source_mode_shares(survey_name, purpose_df, purpose)
                if mode_counts is None:
                    continue

                # Blend into overall rates
                for mode_str, share in mode_counts.items():
                    try:
                        mode_type = ModeType.from_survey_mode(mode_str)
                        if mode_type not in blended_rates:
                            blended_rates[mode_type] = 0.0
                        blended_rates[mode_type] += weight * share
                    except (ValueError, KeyError) as e:
                        logger.debug(f"  Unknown mode '{mode_str}' in survey: {e}")

            if blended_rates:
                # Renormalize (weights may not sum to 1 if some surveys skipped)
                total = sum(blended_rates.values())
                if total > 0:
                    blended_rates = {k: v / total for k, v in blended_rates.items()}

                self.survey_rates[purpose] = blended_rates
                logger.debug(f"  Mode rates for '{purpose}': {self._format_rates(blended_rates)}")
            else:
                logger.debug(f"  No valid data for purpose '{purpose}'")

        # Log summary
        logger.info(f"Computed mode rates for {len(self.survey_rates)} purposes")
        if 'all' in self.survey_rates:
            logger.info(f"  Overall mode distribution: {self._format_rates(self.survey_rates['all'])}")

    def _source_has_driver_info(self, survey_name: str) -> bool:
        """True if the source tells drivers from passengers (has Ride trips)."""
        cache = self.__dict__.setdefault('_driver_info', {})
        if survey_name not in cache:
            df = self.survey_data[survey_name]
            cache[survey_name] = bool('mode_type' in df.columns
                                      and df['mode_type'].eq(MODE_RIDE).any())
            if not cache[survey_name] and ModeType.RIDE in self.mode_configs:
                logger.warning(
                    f"  Survey '{survey_name}' has no driver/passenger split: its Car share is "
                    f"split into car and ride with the NHTS 2022 driver shares per purpose")
        return cache[survey_name]

    def _source_mode_shares(self, survey_name: str, purpose_df: pd.DataFrame,
                            purpose: str) -> Optional[pd.Series]:
        """Mode shares (survey mode label -> share) of one source and purpose.

        Trip-weighted when ``mode_choice.weighted_shares`` is true (default)
        and the source has positive weights. Car passengers (``Ride``):

        * ride enabled, source without a driver field (for example
          ``bham_local``): the ``Car`` share is split with
          NHTS_2022_DRIVER_SHARE of the purpose;
        * ride disabled: ``Ride`` counts as ``Car`` (the old behaviour, every
          passenger drives).
        """
        weights = None
        if self.weighted_shares and 'trip_weight' in purpose_df.columns:
            w = pd.to_numeric(purpose_df['trip_weight'], errors='coerce').fillna(0.0).clip(lower=0)
            if w.sum() > 0:
                weights = w
        modes = purpose_df['mode_type']
        if weights is None:
            shares = modes.value_counts(normalize=True)
        else:
            shares = weights.groupby(modes.values).sum()
            shares = shares / shares.sum()
        shares = shares.copy()

        ride_on = ModeType.RIDE in self.mode_configs
        if not ride_on:
            if MODE_RIDE in shares.index:
                shares[MODE_CAR] = shares.get(MODE_CAR, 0.0) + shares[MODE_RIDE]
                shares = shares.drop(MODE_RIDE)
        elif not self._source_has_driver_info(survey_name) and MODE_CAR in shares.index:
            d = NHTS_2022_DRIVER_SHARE.get(purpose, NHTS_2022_DRIVER_SHARE['all'])
            car = shares[MODE_CAR]
            shares[MODE_CAR] = car * d
            shares[MODE_RIDE] = shares.get(MODE_RIDE, 0.0) + car * (1.0 - d)
        return shares

    def _format_rates(self, rates: Dict[ModeType, float]) -> str:
        """Format rates dict for logging."""
        return ', '.join(f"{k.value}={v:.1%}" for k, v in sorted(rates.items(), key=lambda x: -x[1]))

    def _get_base_rates(self, purpose: Optional[str] = None) -> Dict[ModeType, float]:
        """
        Get base mode rates for a purpose, with fallback to 'all'.

        Args:
            purpose: Trip purpose (e.g., 'Work', 'Shopping')

        Returns:
            Dict mapping ModeType to share (0.0-1.0)
        """
        if not self.survey_rates:
            # No survey data - return 100% for fallback mode
            logger.debug("No survey rates available, using fallback mode")
            return {self.fallback_mode: 1.0}

        # Try purpose-specific rates first
        if purpose and purpose in self.survey_rates:
            return self.survey_rates[purpose].copy()

        # Fall back to overall rates
        if 'all' in self.survey_rates:
            if purpose:
                self.stats['purposes_with_fallback'].add(purpose)
                logger.debug(f"No rates for purpose '{purpose}', using 'all' rates")
            return self.survey_rates['all'].copy()

        # Last resort - fallback mode
        logger.warning("No survey rates found, using fallback mode")
        self.stats['fallback_used'] += 1
        return {self.fallback_mode: 1.0}

    def _apply_rate_adjustments(self, base_rates: Dict[ModeType, float]) -> Dict[ModeType, float]:
        """
        Apply config rate blending and share adjustments to base rates.

        For each mode in config:
        1. If config_rate is set, blend: (1-blend_weight)*survey + blend_weight*config
        2. Apply share_adjustment (additive)

        Args:
            base_rates: Base survey rates {ModeType: share}

        Returns:
            Adjusted rates (not yet renormalized)
        """
        adjusted_rates = base_rates.copy()

        for mode_type, mode_config in self.mode_configs.items():
            # Get current rate (0 if mode not in survey)
            current_rate = adjusted_rates.get(mode_type, 0.0)

            # Step 1: Blend with config_rate if specified
            if mode_config.config_rate is not None:
                survey_rate = current_rate
                if mode_config.survey_rate != 'auto':
                    # Use fixed survey_rate from config instead of computed
                    survey_rate = float(mode_config.survey_rate)

                blended = ((1 - mode_config.blend_weight) * survey_rate +
                          mode_config.blend_weight * mode_config.config_rate)
                current_rate = blended
                # !!! Printed many times !!!
                # logger.debug(f"  {mode_type.value}: blended rate = {blended:.3f} "
                #            f"(survey={survey_rate:.3f}, config={mode_config.config_rate:.3f}, "
                #            f"weight={mode_config.blend_weight:.2f})")

            # Step 2: Apply share_adjustment (additive)
            if mode_config.share_adjustment != 0.0:
                old_rate = current_rate
                current_rate = max(0.0, current_rate + mode_config.share_adjustment)
                logger.debug(f"  {mode_type.value}: adjusted {old_rate:.3f} -> {current_rate:.3f} "
                           f"(adjustment={mode_config.share_adjustment:+.3f})")

            adjusted_rates[mode_type] = current_rate

        return adjusted_rates

    def _filter_and_renormalize(self, rates: Dict[ModeType, float],
                                 available_modes: Set[ModeType]) -> Dict[ModeType, float]:
        """
        Filter rates to available modes and renormalize to sum to 1.0.

        Args:
            rates: Mode rates (may not sum to 1.0)
            available_modes: Set of available ModeTypes for this OD pair

        Returns:
            Filtered and normalized rates
        """
        # Filter to available modes
        filtered = {k: v for k, v in rates.items() if k in available_modes and v > 0}

        if not filtered:
            # No available modes with positive rates - use fallback
            if self.fallback_mode in available_modes:
                logger.debug("No modes with positive rates available, using fallback")
                return {self.fallback_mode: 1.0}
            else:
                # Fallback not available either - use first available
                first_available = min(available_modes, key=lambda m: m.value,
                                      default=self.fallback_mode)
                logger.warning(f"Fallback mode not available, using {first_available.value}")
                return {first_available: 1.0}

        # Renormalize
        total = sum(filtered.values())
        if total > 0:
            filtered = {k: v / total for k, v in filtered.items()}

        return filtered

    def _sample_mode(self, rates: Dict[ModeType, float],
                     rng: Optional[np.random.Generator] = None) -> ModeType:
        """
        Sample a mode from the rate distribution.

        Args:
            rates: Normalized mode rates (should sum to 1.0)
            rng: Random number generator

        Returns:
            Sampled ModeType
        """
        if not rates:
            return self.fallback_mode

        if rng is None:
            rng = self.rng

        modes = list(rates.keys())
        probs = list(rates.values())

        # Sample
        idx = rng.choice(len(modes), p=probs)
        selected = modes[idx]

        # Update stats
        self.stats['mode_samples'][selected] += 1

        return selected

    def choose_mode(self, origin: Location, destination: Location,
                    purpose: Optional[str] = None,
                    rng: Optional[np.random.Generator] = None) -> ModeType:
        """
        Select mode for a single trip.

        Process:
        1. Get available modes for this OD pair
        2. Get base survey rates for the purpose
        3. Apply config rate blending and share adjustments
        4. Filter to available modes and renormalize
        5. Sample mode from distribution

        Args:
            origin: Trip origin location
            destination: Trip destination location
            purpose: Optional trip purpose (e.g., 'Work', 'Shopping')
            rng: Random number generator for reproducibility

        Returns:
            Selected ModeType
        """
        # Step 1: Get available modes
        available_modes = self.availability_manager.get_available_modes(origin, destination)
        if not available_modes:
            logger.warning("No modes available for OD pair, using fallback")
            self.stats['fallback_used'] += 1
            return self.fallback_mode

        logger.debug(f"Available modes for trip: {[m.value for m in available_modes]}")

        # Step 2: Get base survey rates
        base_rates = self._get_base_rates(purpose)

        # Step 3: Apply adjustments
        adjusted_rates = self._apply_rate_adjustments(base_rates)

        # Step 4: Filter and renormalize
        final_rates = self._filter_and_renormalize(adjusted_rates, available_modes)

        logger.debug(f"Final rates for purpose '{purpose}': {self._format_rates(final_rates)}")

        # Step 5: Sample
        return self._sample_mode(final_rates, rng)

    def choose_modes_for_chain(self, activities: List[Any],
                                locations: List[Location],
                                rng: Optional[np.random.Generator] = None) -> List[ModeType]:
        """
        Choose modes for an activity chain.

        For n activities, there are n-1 legs (trips between activities).

        With chain_consistency=True, the entire chain uses one "primary" mode.
        Short legs (haversine distance below `walk_passthrough_max_meters`)
        are exempt from the chain-mode constraint: they are NOT used to
        constrain the chain intersection (a midday Work->Lunch leg won't
        knock PT or car out of the chain) and they are emitted as walk
        regardless of the primary mode (you don't drive 300m to lunch).

        If `final_rates` ends up empty after filtering and renormalisation
        (rare - e.g. dominant_purpose has zero survey mass on every available
        mode), we re-sample using the overall 'all' rates as a retry, up to
        `max_chain_mode_retries` times, before falling back to fallback_mode.

        Args:
            activities: List of Activity objects (must have 'type' attribute)
            locations: List of Location objects (one per activity)
            rng: Random number generator for reproducibility

        Returns:
            List of ModeType for each leg (length = len(activities) - 1)
        """
        if len(activities) < 2:
            return []

        num_legs = len(activities) - 1
        self.stats['chain_length_counts'][num_legs] = (
            self.stats['chain_length_counts'].get(num_legs, 0) + 1
        )

        if rng is None:
            rng = self.rng

        if not self.chain_consistency:
            # No consistency - choose mode independently for each leg
            modes = []
            for i in range(num_legs):
                origin = locations[i]
                destination = locations[i + 1]
                purpose = getattr(activities[i + 1], 'type', None)
                mode = self.choose_mode(origin, destination, purpose, rng)
                modes.append(mode)
            return modes

        # --- Chain consistency path ---
        # First pass: per-leg availability + walk-pass-through classification.
        #
        # Walk-pass-through is intended for short INTERIOR legs of a subtour
        # (e.g. Work->Lunch in Home->Work->Lunch->Work->Home), not for the
        # primary commute legs that bookend the chain. A leg is eligible
        # for walk-pass only if NEITHER of its endpoints is a Home activity:
        # otherwise short Home->Work commutes get auto-converted to walk
        # regardless of survey mode shares, which inflates walk share well
        # beyond what the survey supports.
        leg_available_sets: List[Set[ModeType]] = []
        is_short_leg: List[bool] = []
        for i in range(num_legs):
            origin = locations[i]
            destination = locations[i + 1]
            leg_available = self.availability_manager.get_available_modes(origin, destination)
            leg_available_sets.append(leg_available)
            for mt in leg_available:
                self.stats['mode_eligible_per_leg'][mt] = (
                    self.stats['mode_eligible_per_leg'].get(mt, 0) + 1
                )

            short = False
            if self.walk_passthrough_max_meters > 0:
                origin_type = getattr(activities[i], 'type', None)
                dest_type = getattr(activities[i + 1], 'type', None)
                is_interior = origin_type != 'Home' and dest_type != 'Home'
                if is_interior:
                    dist_m = haversine_meters(
                        origin.lat, origin.lon, destination.lat, destination.lon
                    )
                    short = dist_m <= self.walk_passthrough_max_meters
            is_short_leg.append(short)

        # Intersect availability across only the LONG legs (short legs get a
        # walk pass and don't constrain the chain mode).
        long_leg_indices = [i for i, s in enumerate(is_short_leg) if not s]
        if long_leg_indices:
            available_for_all: Set[ModeType] = leg_available_sets[long_leg_indices[0]].copy()
            for i in long_leg_indices[1:]:
                available_for_all &= leg_available_sets[i]
        else:
            # All legs are short - union over per-leg availability is fine,
            # since each leg will be emitted as walk anyway. Pick walk if
            # available, otherwise any mode (sampling will pick one).
            available_for_all = set()
            for s in leg_available_sets:
                available_for_all |= s

        # Diagnostics: for each mode, was it eligible on every long leg
        # individually (i.e. survived the intersection)? And: did walk-pass
        # rescue it from a short leg that would otherwise have filtered it?
        any_short = any(is_short_leg)
        if any_short:
            self.stats['walk_passthrough_chains'] += 1
            self.stats['walk_passthrough_legs'] += sum(is_short_leg)

        # Compare full intersection (all legs, no walk-pass) vs. long-leg
        # intersection to count modes "saved" by walk-pass-through.
        full_intersect: Set[ModeType] = leg_available_sets[0].copy()
        for s in leg_available_sets[1:]:
            full_intersect &= s
        rescued_modes = available_for_all - full_intersect
        for mt in rescued_modes:
            self.stats['mode_lost_to_chain_consistency'][mt] = (
                self.stats['mode_lost_to_chain_consistency'].get(mt, 0) + 1
            )
        for mt in available_for_all:
            self.stats['mode_eligible_after_intersection'][mt] = (
                self.stats['mode_eligible_after_intersection'].get(mt, 0) + 1
            )

        if not available_for_all:
            logger.warning("No mode available for all legs in chain, using fallback for each leg")
            self.stats['fallback_used'] += 1
            return self._emit_chain_modes(self.fallback_mode, is_short_leg, leg_available_sets)

        # Track availability combinations for summary.
        avail_key = frozenset(m.value for m in available_for_all)
        self.stats['chain_availability'][avail_key] = self.stats['chain_availability'].get(avail_key, 0) + 1

        # Get the dominant purpose for mode choice (use first non-Home activity).
        dominant_purpose = None
        for act in activities[1:]:
            act_type = getattr(act, 'type', None)
            if act_type and act_type != 'Home':
                dominant_purpose = act_type
                break

        # Sample chain mode, with retry if filter+renormalise yields empty rates.
        chain_mode: Optional[ModeType] = None
        purposes_to_try = [dominant_purpose, 'all'] if dominant_purpose else ['all']
        attempts = 0
        for purpose_attempt in purposes_to_try:
            if attempts >= self.max_chain_mode_retries:
                break
            attempts += 1
            if attempts > 1:
                self.stats['chain_retry_attempts'] += 1
            base_rates = self._get_base_rates(purpose_attempt)
            adjusted_rates = self._apply_rate_adjustments(base_rates)
            final_rates = self._filter_and_renormalize(adjusted_rates, available_for_all)
            if final_rates and sum(final_rates.values()) > 0:
                chain_mode = self._sample_mode(final_rates, rng)
                # _sample_mode bumps mode_samples once; back it out so the
                # per-leg accounting in _emit_chain_modes is the single source
                # of truth for chain paths. (choose_mode still relies on the
                # _sample_mode bump for single-trip callers.)
                self.stats['mode_samples'][chain_mode] -= 1
                if attempts > 1:
                    self.stats['chain_retry_succeeded'] += 1
                break

        if chain_mode is None:
            # All retry attempts produced empty rates - pick uniformly from
            # the available set as a last resort before fallback.
            self.stats['chain_retry_exhausted'] += 1
            if available_for_all:
                avail_sorted = sorted(available_for_all, key=lambda m: m.value)
                chain_mode = avail_sorted[int(rng.integers(0, len(avail_sorted)))]
            else:
                chain_mode = self.fallback_mode
                self.stats['fallback_used'] += 1

        # Track chain mode selections for summary.
        sel_key = (chain_mode.value, dominant_purpose, num_legs)
        self.stats['chain_mode_selections'][sel_key] = self.stats['chain_mode_selections'].get(sel_key, 0) + 1

        return self._emit_chain_modes(chain_mode, is_short_leg, leg_available_sets)

    def _emit_chain_modes(self, chain_mode: ModeType,
                          is_short_leg: List[bool],
                          leg_available_sets: List[Set[ModeType]]) -> List[ModeType]:
        """Emit per-leg modes from a primary chain mode, applying walk-pass-through.

        Short legs emit as WALK if walk is available on that leg; otherwise
        they emit as the chain mode (e.g. walk disabled in config). Long
        legs always emit as the chain mode - by construction they're in
        the chain intersection.
        """
        modes: List[ModeType] = []
        for i, short in enumerate(is_short_leg):
            if short and ModeType.WALK in leg_available_sets[i]:
                modes.append(ModeType.WALK)
                self.stats['mode_samples'][ModeType.WALK] += 1
            else:
                modes.append(chain_mode)
                self.stats['mode_samples'][chain_mode] += 1
        return modes

    def get_output_mode(self, mode_type: ModeType, output_format: str = 'matsim') -> str:
        """
        Get the output format mode string for a ModeType.

        Args:
            mode_type: The mode type
            output_format: Target format ('matsim', etc.)

        Returns:
            Mode string for output (e.g., 'car', 'pt')
        """
        mode_config = self.mode_configs.get(mode_type)
        if mode_config and output_format == 'matsim':
            return mode_config.matsim_mode
        return mode_type.to_output_mode(output_format)

    def create_legs(self, activities: List[Any],
                    locations: List[Location],
                    rng: Optional[np.random.Generator] = None,
                    output_format: str = 'matsim') -> List[Leg]:
        """
        Create Leg objects for an activity chain.

        Convenience method that combines mode choice with Leg creation.

        Args:
            activities: List of Activity objects
            locations: List of Location objects
            rng: Random number generator
            output_format: Target output format

        Returns:
            List of Leg objects with mode strings
        """
        mode_types = self.choose_modes_for_chain(activities, locations, rng)
        return [Leg(mode=self.get_output_mode(mt, output_format)) for mt in mode_types]

    def get_stats_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for logging.

        Returns:
            Dict with mode choice statistics
        """
        total_samples = sum(self.stats['mode_samples'].values())
        mode_distribution = {}
        if total_samples > 0:
            mode_distribution = {
                k.value: v / total_samples
                for k, v in self.stats['mode_samples'].items()
                if v > 0
            }

        # Aggregate chain selections by mode and by purpose
        chain_by_mode = {}
        chain_by_purpose = {}
        for (mode, purpose, num_legs), count in self.stats['chain_mode_selections'].items():
            chain_by_mode[mode] = chain_by_mode.get(mode, 0) + count
            purpose_key = purpose or 'Unknown'
            chain_by_purpose[purpose_key] = chain_by_purpose.get(purpose_key, 0) + count

        # Aggregate availability combinations
        avail_summary = {}
        for modes_set, count in self.stats['chain_availability'].items():
            key = ', '.join(sorted(modes_set))
            avail_summary[key] = avail_summary.get(key, 0) + count

        # Chain-consistency diagnostics: per-mode eligibility leak.
        # leak_pct = (eligible per-leg basis - eligible after intersection) /
        #             eligible per-leg basis. The "per-leg basis" is the count
        #             of legs where the mode was individually available; the
        #             intersection count is per-chain (one per chain), so we
        #             multiply each chain by its length to compare. Since
        #             chain_availability tracks unique (frozenset, count)
        #             pairs we approximate using mode_eligible_after_intersection
        #             (chain count, not leg count).
        eligible_per_leg = {
            k.value: v for k, v in self.stats['mode_eligible_per_leg'].items() if v > 0
        }
        eligible_after_intersect = {
            k.value: v for k, v in self.stats['mode_eligible_after_intersection'].items() if v > 0
        }
        rescued_by_walk = {
            k.value: v for k, v in self.stats['mode_lost_to_chain_consistency'].items() if v > 0
        }

        return {
            'total_mode_choices': total_samples,
            'mode_distribution': mode_distribution,
            'fallback_used': self.stats['fallback_used'],
            'chain_retries': self.stats['chain_retries'],
            'purposes_using_fallback_rates': list(self.stats['purposes_with_fallback']),
            'chain_selections_by_mode': chain_by_mode,
            'chain_selections_by_purpose': chain_by_purpose,
            'chain_availability_combos': avail_summary,
            # New diagnostics
            'mode_eligible_per_leg': eligible_per_leg,
            'mode_eligible_chains_after_intersection': eligible_after_intersect,
            'mode_rescued_by_walk_passthrough_chains': rescued_by_walk,
            'chain_length_counts': dict(self.stats['chain_length_counts']),
            'walk_passthrough_legs': self.stats['walk_passthrough_legs'],
            'walk_passthrough_chains': self.stats['walk_passthrough_chains'],
            'chain_retry_attempts': self.stats['chain_retry_attempts'],
            'chain_retry_succeeded': self.stats['chain_retry_succeeded'],
            'chain_retry_exhausted': self.stats['chain_retry_exhausted'],
        }

    def log_stats_summary(self) -> None:
        """Log summary statistics."""
        stats = self.get_stats_summary()
        logger.info("=" * 50)
        logger.info("MODE CHOICE STATISTICS")
        logger.info("=" * 50)
        logger.info(f"  Total mode choices: {stats['total_mode_choices']}")
        logger.info(f"  Fallback mode used: {stats['fallback_used']} times")
        logger.info(f"  Chain retries: {stats['chain_retries']}")

        if stats['mode_distribution']:
            logger.info("  Mode distribution in generated plans:")
            for mode, share in sorted(stats['mode_distribution'].items(), key=lambda x: -x[1]):
                logger.info(f"    {mode}: {share:.1%}")

        if stats['purposes_using_fallback_rates']:
            logger.info(f"  Purposes using 'all' rates: {stats['purposes_using_fallback_rates']}")

        if stats.get('chain_selections_by_mode'):
            logger.info("  Chain mode selections:")
            for mode, count in sorted(stats['chain_selections_by_mode'].items(), key=lambda x: -x[1]):
                logger.info(f"    {mode}: {count}")

        if stats.get('chain_selections_by_purpose'):
            logger.info("  Chain selections by purpose:")
            for purpose, count in sorted(stats['chain_selections_by_purpose'].items(), key=lambda x: -x[1]):
                logger.info(f"    {purpose}: {count}")

        if stats.get('chain_availability_combos'):
            logger.info("  Mode availability combinations across chains:")
            for combo, count in sorted(stats['chain_availability_combos'].items(), key=lambda x: -x[1]):
                logger.info(f"    [{combo}]: {count} chains")

        # --- Chain-consistency diagnostics ---
        chain_lengths = stats.get('chain_length_counts') or {}
        if chain_lengths:
            logger.info("  Chain length distribution (legs per chain):")
            for length, count in sorted(chain_lengths.items()):
                logger.info(f"    {length}-leg chains: {count}")

        per_leg = stats.get('mode_eligible_per_leg') or {}
        per_chain = stats.get('mode_eligible_chains_after_intersection') or {}
        if per_leg:
            logger.info("  Per-mode eligibility (chain-consistency leak):")
            logger.info("    mode: eligible_legs / chains_surviving_intersection")
            for mode in sorted(per_leg.keys()):
                legs = per_leg.get(mode, 0)
                chains = per_chain.get(mode, 0)
                logger.info(f"    {mode}: {legs} eligible legs, {chains} chains survived")

        rescued = stats.get('mode_rescued_by_walk_passthrough_chains') or {}
        if rescued:
            logger.info("  Modes rescued by walk-pass-through (chains where short")
            logger.info("  legs would otherwise have filtered the mode out):")
            for mode, count in sorted(rescued.items(), key=lambda x: -x[1]):
                logger.info(f"    {mode}: rescued in {count} chains")

        wp_legs = stats.get('walk_passthrough_legs', 0)
        wp_chains = stats.get('walk_passthrough_chains', 0)
        if wp_legs or wp_chains:
            logger.info(f"  Walk-pass-through: {wp_legs} short legs across "
                       f"{wp_chains} chains emitted as walk")

        retry_att = stats.get('chain_retry_attempts', 0)
        if retry_att:
            logger.info(f"  Chain mode retries: {retry_att} attempts, "
                       f"{stats.get('chain_retry_succeeded', 0)} succeeded, "
                       f"{stats.get('chain_retry_exhausted', 0)} exhausted")

        logger.info("=" * 50)
