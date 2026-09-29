"""Person-first demand budget.

One place that decides how many persons of each segment travel on the modelled
day, and what they do. The work generator, the non-work generators and the
recommender read it, so the demand they report is the same demand that is
generated. Design: TECHNICAL_REPORT.md, section 5.2.

Roles of the sources:
  * Census + LODES RAC (home_locations): persons and workers per home block.
  * County ACS B01001: splits non-workers into children 0-4, students 5-17
    and adults (a fixed national split is used when ACS is unavailable).
  * Survey person-days: for each segment, the share of days that are commute
    days, other travel days and no-travel days, and the main purpose of the
    other travel days. Blended across surveys with data.surveys[].weight.
  * LODES OD stays the work-place distribution; the work generator multiplies
    it by P(commute) of workers (see models/plan_generator.py).

User controls act on top of the survey values; the neutral value keeps the
survey as it is:
  * plan_generation.work_scaling_multiplier (1.0) — applied by the work generator
  * nonwork_purposes.nonwork_trip_share (1.0) — x P(travel) of non-commute days
  * nonwork_purposes.<P>.trip_generation.config_rate + blend_weight (0) —
    blends the per-person daily rate of P-main travel days toward config_rate
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from data_sources.base_survey_trip import BaseSurveyTrip
from utils.logger import setup_logger

logger = setup_logger(__name__)

B = BaseSurveyTrip
TRAVEL_SEGMENTS = (B.SEG_WORKER, B.SEG_STUDENT, B.SEG_NONWORKER_ADULT)

# Used only when ACS B01001 cannot be fetched (2020 Census, United States).
NATIONAL_AGE_SHARES = {'age_0_4': 0.057, 'age_5_17': 0.164}

ACS_URL = "https://api.census.gov/data/{year}/acs/acs5"
ACS_YEAR = 2023
_B01001_UNDER5 = ["B01001_003E", "B01001_027E"]
_B01001_5_17 = ["B01001_004E", "B01001_005E", "B01001_006E",
                "B01001_028E", "B01001_029E", "B01001_030E"]


# ── Helpers ─────────────────────────────────────────────────────────────

def main_purpose(trips: pd.DataFrame) -> Optional[str]:
    """Main activity of a day: the non-Home, non-Work stop with the longest dwell.

    Dwell = next departure - this arrival. The last stop of a day that does
    not end at Home has no known dwell and counts as 0. Ties go to the first
    stop. Returns None when the day has no such stop.
    """
    t = trips.sort_values(B.DEPART_TIME)
    dests = t[B.DESTINATION_PURPOSE].tolist()
    arrive = pd.to_datetime(t[B.ARRIVE_TIME]).tolist()
    depart = pd.to_datetime(t[B.DEPART_TIME]).tolist()
    best, best_dwell = None, -1.0
    for i, act in enumerate(dests):
        if act in (B.ACT_HOME, B.ACT_WORK):
            continue
        dwell = (depart[i + 1] - arrive[i]).total_seconds() if i + 1 < len(dests) else 0.0
        if dwell > best_dwell:
            best, best_dwell = act, dwell
    return best


def _day_weight(trips: pd.DataFrame, use_weight: bool) -> float:
    """The chain weight process_trip_chains() gives a day (mean trip weight)."""
    if not use_weight or B.TRIP_WEIGHT not in trips.columns:
        return 1.0
    w = pd.to_numeric(trips[B.TRIP_WEIGHT], errors='coerce')
    w = w[w > 0]
    return float(w.mean()) if len(w) else 0.0


def fetch_county_age_shares(config: Dict) -> Tuple[Dict[str, Dict[str, float]], str]:
    """Share of population aged 0-4 and 5-17 per county (ACS 5-year B01001).

    Cached in <data_dir>/acs_cache/. Returns ({county_fips: shares}, source);
    counties the API did not return get the national split.
    """
    counties = sorted(config.get('region', {}).get('counties', []))
    key = hashlib.sha256(",".join(counties).encode()).hexdigest()[:12]
    cache = Path(config['data']['data_dir']) / 'acs_cache' / f'B01001_{ACS_YEAR}_{key}.json'
    if cache.exists():
        try:
            return json.loads(cache.read_text()), f"ACS {ACS_YEAR} B01001 (cache)"
        except Exception:
            pass

    shares: Dict[str, Dict[str, float]] = {}
    try:
        import requests
        api_key = (config.get('data', {}).get('census_api_key') or '').strip()
        variables = ["B01001_001E"] + _B01001_UNDER5 + _B01001_5_17
        by_state: Dict[str, List[str]] = {}
        for fips in counties:
            by_state.setdefault(fips[:2], []).append(fips[2:])
        for state, cty in by_state.items():
            params = {"get": ",".join(variables), "for": f"county:{','.join(cty)}",
                      "in": f"state:{state}"}
            if api_key:
                params["key"] = api_key
            resp = None
            for attempt in range(3):
                try:
                    resp = requests.get(ACS_URL.format(year=ACS_YEAR), params=params, timeout=60)
                    if resp.status_code < 500:
                        break
                except requests.RequestException:
                    resp = None
            if resp is None or 'json' not in resp.headers.get('content-type', ''):
                logger.warning(f"ACS B01001: no usable response for state {state}")
                continue
            rows = resp.json()
            head = rows[0]
            for row in rows[1:]:
                r = dict(zip(head, row))
                total = float(r["B01001_001E"] or 0)
                if total <= 0:
                    continue
                shares[state + r["county"]] = {
                    'age_0_4': sum(float(r[v] or 0) for v in _B01001_UNDER5) / total,
                    'age_5_17': sum(float(r[v] or 0) for v in _B01001_5_17) / total,
                }
    except Exception as e:
        logger.warning(f"ACS B01001 fetch failed: {e}")

    if shares:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(shares, indent=1))
        except Exception:
            pass
        source = f"ACS {ACS_YEAR} B01001"
    else:
        source = "FALLBACK national 2020 Census split"
        logger.warning(f"Age split of non-workers: {source} "
                       f"(0-4: {NATIONAL_AGE_SHARES['age_0_4']:.1%}, "
                       f"5-17: {NATIONAL_AGE_SHARES['age_5_17']:.1%})")
    missing = [c for c in counties if c not in shares]
    for c in missing:
        shares[c] = dict(NATIONAL_AGE_SHARES)
    if missing and len(missing) < len(counties):
        logger.warning(f"ACS B01001 missing for {missing}; national split used there")
    return shares, source


def enabled_purposes(config: Dict) -> List[str]:
    return [p for p, c in config.get('nonwork_purposes', {}).items()
            if isinstance(c, dict) and c.get('enabled', False)]


# ── Budget ──────────────────────────────────────────────────────────────

class DemandBudget:
    """Result of compute_demand_budget(). See the module docstring."""

    def __init__(self):
        self.p_commute: float = 1.0
        self.segment_probs: Dict[str, Dict[str, float]] = {}      # blended
        self.segment_probs_by_source: Dict[str, Dict[str, Dict[str, float]]] = {}
        self.purpose_mix: Dict[str, Dict[str, float]] = {}        # seg -> P -> share of other-travel days
        self.purpose_rates: Dict[str, Dict[str, float]] = {}      # seg -> P -> per person per day
        self.segment_population: Dict[str, float] = {}
        self.purpose_origin_totals: Dict[str, float] = {}         # P -> unscaled persons
        self.purpose_factors: Dict[str, float] = {}               # P -> knob factor applied
        self.purpose_chains_dfs: Dict[str, pd.DataFrame] = {}     # merged sources
        self.per_source_purpose_chains_dfs: Dict[str, Dict[str, pd.DataFrame]] = {}
        self.age_source: str = ''
        self.notes: List[str] = []

    def origin_key(self, purpose: str) -> str:
        return origin_key(purpose)

    def summary(self) -> Dict[str, Any]:
        r = lambda x: round(float(x), 5)
        return {
            'p_commute_workers': r(self.p_commute),
            'segment_population': {k: round(v) for k, v in self.segment_population.items()},
            'segment_probs': {s: {k: r(v) for k, v in d.items()} for s, d in self.segment_probs.items()},
            'segment_probs_by_source': {src: {s: {k: r(v) for k, v in d.items()} for s, d in sd.items()}
                                        for src, sd in self.segment_probs_by_source.items()},
            'purpose_mix': {s: {p: r(v) for p, v in d.items()} for s, d in self.purpose_mix.items()},
            'purpose_rates_per_person_day': {s: {p: r(v) for p, v in d.items()}
                                             for s, d in self.purpose_rates.items()},
            'nonwork_persons_unscaled': {p: round(v) for p, v in self.purpose_origin_totals.items()},
            'knob_factors': {p: r(v) for p, v in self.purpose_factors.items()},
            'age_split_source': self.age_source,
            'notes': self.notes,
        }


def origin_key(purpose: str) -> str:
    """home_locs_dict key holding the expected unscaled P-main travellers of a block."""
    return f"nw_origin_{purpose}"


def _day_key(pid: str, date: Optional[str], dated: bool):
    return (pid, date) if dated else pid


def _source_day_records(persons: Dict, person_days: Optional[pd.DataFrame],
                        purposes: List[str], use_weight: bool) -> pd.DataFrame:
    """One row per surveyed travel day with trips: key, segment, commute, main purpose, chain weight."""
    seg_of: Dict[Any, str] = {}
    pdw_of: Dict[Any, float] = {}
    dated = False
    if person_days is not None:
        dated = person_days[B.PD_DATE].notna().any()
        for pid, date, seg, w in zip(person_days[B.PD_PERSON_ID].astype(str),
                                     person_days[B.PD_DATE],
                                     person_days[B.PD_SEGMENT],
                                     person_days[B.PD_WEIGHT]):
            k = _day_key(pid, str(date) if dated else None, dated)
            seg_of[k] = seg
            pdw_of[k] = float(w)

    fallback_purpose = B.ACT_OTHER if B.ACT_OTHER in purposes else None
    rows = []
    for pid, days in persons.items():
        for date, trips in days.items():
            if trips.empty:
                continue
            k = _day_key(str(pid), str(date), dated)
            commute = bool((trips[B.DESTINATION_PURPOSE] == B.ACT_WORK).any())
            mp = None if commute else main_purpose(trips)
            if mp is not None and mp not in purposes:
                mp = fallback_purpose
            rows.append((k, seg_of.get(k), commute, mp,
                         _day_weight(trips, use_weight), pdw_of.get(k)))
    return pd.DataFrame(rows, columns=['key', 'segment', 'commute', 'main_purpose',
                                       'chain_weight', 'pd_weight'])


def _segment_probs(person_days: pd.DataFrame, days: pd.DataFrame,
                   purposes: List[str]) -> Tuple[Dict, Dict]:
    """Day-type probabilities and purpose mix per segment for one source."""
    probs, mix = {}, {}
    matched = days[days['pd_weight'].notna()]
    for seg in TRAVEL_SEGMENTS:
        pdx = person_days[person_days[B.PD_SEGMENT] == seg]
        w_all = pdx[B.PD_WEIGHT].sum()
        if w_all <= 0:
            continue
        p_travel = pdx.loc[pdx[B.PD_N_TRIPS] > 0, B.PD_WEIGHT].sum() / w_all
        m = matched[matched['segment'] == seg]
        w_travel = m['pd_weight'].sum()
        c = m.loc[m['commute'], 'pd_weight'].sum() / w_travel if w_travel > 0 else 0.0
        probs[seg] = {'travel': p_travel, 'commute': p_travel * c,
                      'other_travel': p_travel * (1 - c), 'no_travel': 1 - p_travel,
                      'person_days': int(len(pdx))}
        other = m[~m['commute'] & m['main_purpose'].notna()]
        w_other = other['pd_weight'].sum()
        mix[seg] = {p: (other.loc[other['main_purpose'] == p, 'pd_weight'].sum() / w_other
                        if w_other > 0 else 0.0) for p in purposes}
    return probs, mix


def _blend(per_source: Dict[str, Dict[str, Dict[str, float]]], weights: Dict[str, float]):
    """Weighted mean of nested {seg: {k: v}} dicts over sources."""
    out: Dict[str, Dict[str, float]] = {}
    for seg in TRAVEL_SEGMENTS:
        items = [(weights[s], d[seg]) for s, d in per_source.items() if seg in d and weights.get(s, 0) > 0]
        tot = sum(w for w, _ in items)
        if tot <= 0:
            continue
        keys = set().union(*(d.keys() for _, d in items))
        out[seg] = {k: sum(w * d.get(k, 0.0) for w, d in items) / tot for k in keys}
    return out


def compute_demand_budget(config: Dict,
                          survey_manager=None,
                          persons_by_source: Optional[Dict[str, Dict]] = None,
                          home_locs_dict: Optional[Dict[str, Dict]] = None,
                          build_chains: bool = True) -> DemandBudget:
    """Compute the budget and write per-block non-work origins into home_locs_dict.

    Missing inputs are loaded. ``home_locs_dict`` is modified in place: each
    block gets ``nw_origin_<P>`` for every enabled purpose.
    """
    from data_sources.survey_manager import SurveyManager
    from models.chains import process_trip_chains

    if survey_manager is None:
        survey_manager = SurveyManager(config)
    if persons_by_source is None:
        persons_by_source = survey_manager.process_persons()
    if home_locs_dict is None:
        from models.home_locs_v2 import load_home_locations_by_counties
        home_locs_dict = load_home_locations_by_counties(config)

    budget = DemandBudget()
    purposes = enabled_purposes(config)
    use_weight = config.get('chains', {}).get('use_weighted_chains', True)
    person_days = survey_manager.get_person_days()
    blend_weights = survey_manager.get_blend_weights()

    # ── Day records and per-source day-type probabilities ──────────────
    day_records: Dict[str, pd.DataFrame] = {}
    probs_by_source, mix_by_source = {}, {}
    for src, persons in persons_by_source.items():
        day_records[src] = _source_day_records(persons, person_days.get(src), purposes, use_weight)
        if person_days.get(src) is not None:
            probs_by_source[src], mix_by_source[src] = _segment_probs(
                person_days[src], day_records[src], purposes)
            unmatched = day_records[src]['pd_weight'].isna().mean()
            if unmatched > 0.02:
                budget.notes.append(f"{src}: {unmatched:.1%} of travel days have no person-day row")

    if not probs_by_source:
        raise ValueError(
            "No active survey provides person-days, so the model cannot know how "
            "often each segment travels. Add 'person_file' (NHTS) or "
            "'person_file' + 'day_file' (TBI) to data.surveys[] of a survey with "
            "weight > 0.")

    pd_weights = {s: blend_weights.get(s, 0.0) for s in probs_by_source}
    budget.segment_probs_by_source = probs_by_source
    budget.segment_probs = _blend(probs_by_source, pd_weights)
    budget.purpose_mix = _blend(mix_by_source, pd_weights)
    for seg in TRAVEL_SEGMENTS:
        if seg not in budget.segment_probs:
            raise ValueError(f"Survey person-days have no '{seg}' segment; cannot build the budget")

    budget.p_commute = budget.segment_probs[B.SEG_WORKER]['commute']
    for seg in (B.SEG_STUDENT, B.SEG_NONWORKER_ADULT):
        dropped = budget.segment_probs[seg]['commute']
        if dropped > 0.005:
            budget.notes.append(f"{seg}: {dropped:.1%} of days are commute days; work plans come "
                                f"from LODES workers only, so these are not generated")

    nw_cfg = config.get('nonwork_purposes', {})
    share_knob = float(nw_cfg.get('nonwork_trip_share', 1.0))
    budget.purpose_rates = {
        seg: {p: budget.segment_probs[seg]['other_travel'] * budget.purpose_mix.get(seg, {}).get(p, 0.0)
              for p in purposes}
        for seg in TRAVEL_SEGMENTS}

    # ── Persons per block and segment ──────────────────────────────────
    age_shares, budget.age_source = fetch_county_age_shares(config)
    seg_pop = {s: 0.0 for s in (*TRAVEL_SEGMENTS, B.SEG_CHILD)}
    block_segs: Dict[str, Tuple[float, float, float]] = {}
    for bid, d in home_locs_dict.items():
        workers = float(d.get('n_employees', 0) or 0)
        non_emp = float(d.get('non_employees', 0) or 0)
        pop = workers + non_emp
        county = (d.get('state_fips', '') or '') + (d.get('county_fips', '') or '')
        sh = age_shares.get(county) or age_shares.get(bid[:5]) or NATIONAL_AGE_SHARES
        child, student = pop * sh['age_0_4'], pop * sh['age_5_17']
        if child + student > non_emp and child + student > 0:
            f = non_emp / (child + student)
            child, student = child * f, student * f
        adult = max(0.0, non_emp - child - student)
        block_segs[bid] = (workers, student, adult)
        seg_pop[B.SEG_WORKER] += workers
        seg_pop[B.SEG_STUDENT] += student
        seg_pop[B.SEG_NONWORKER_ADULT] += adult
        seg_pop[B.SEG_CHILD] += child
    budget.segment_population = seg_pop
    total_pop = sum(seg_pop.values())

    # ── Knob factors per purpose ───────────────────────────────────────
    for p in purposes:
        base = sum(seg_pop[s] * budget.purpose_rates[s][p] for s in TRAVEL_SEGMENTS) * share_knob
        rate = base / total_pop if total_pop > 0 else 0.0
        tg = nw_cfg.get(p, {}).get('trip_generation', {})
        w = float(tg.get('blend_weight', 0) or 0)
        cfg_rate = tg.get('config_rate')
        factor = share_knob
        if w > 0 and cfg_rate is not None and rate > 0:
            factor *= ((1 - w) * rate + w * float(cfg_rate)) / rate
        budget.purpose_factors[p] = factor

    # ── Per-block origins ──────────────────────────────────────────────
    totals = {p: 0.0 for p in purposes}
    for bid, (workers, student, adult) in block_segs.items():
        d = home_locs_dict[bid]
        for p in purposes:
            v = (workers * budget.purpose_rates[B.SEG_WORKER][p]
                 + student * budget.purpose_rates[B.SEG_STUDENT][p]
                 + adult * budget.purpose_rates[B.SEG_NONWORKER_ADULT][p]) * budget.purpose_factors[p]
            d[origin_key(p)] = v
            totals[p] += v
    budget.purpose_origin_totals = totals

    # ── Chain pools per main purpose, re-weighted to the region's segment mix ──
    if build_chains:
        for src, persons in persons_by_source.items():
            days = day_records[src]
            weights: Dict[Any, Tuple[str, float]] = {}
            for p in purposes:
                pool = days[~days['commute'] & (days['main_purpose'] == p)]
                if pool.empty:
                    continue
                target = {s: seg_pop[s] * budget.purpose_rates[s][p] for s in TRAVEL_SEGMENTS}
                t_tot = sum(target.values())
                has_seg = pool['segment'].isin(TRAVEL_SEGMENTS)
                s_tot = pool.loc[has_seg, 'chain_weight'].sum()
                factor = {}
                for s in TRAVEL_SEGMENTS:
                    s_share = pool.loc[pool['segment'] == s, 'chain_weight'].sum() / s_tot if s_tot > 0 else 0
                    factor[s] = (target[s] / t_tot) / s_share if (t_tot > 0 and s_share > 0) else 0.0
                for k, seg, cw in zip(pool['key'], pool['segment'], pool['chain_weight']):
                    # A source without person-days has no segments: keep its weight.
                    weights[k] = (p, cw * factor[seg] if seg in factor else cw)
            dated = person_days.get(src) is not None and person_days[src][B.PD_DATE].notna().any()

            per_purpose = {}
            for p in purposes:
                def fn(pid, date, trips, w, _p=p):
                    hit = weights.get(_day_key(str(pid), str(date), dated))
                    return hit[1] if hit and hit[0] == _p else 0.0
                recs = process_trip_chains(persons, use_weight=use_weight, weight_fn=fn)
                if recs:
                    per_purpose[p] = pd.DataFrame(recs)
            budget.per_source_purpose_chains_dfs[src] = per_purpose

        for p in purposes:
            frames = [d[p] for d in budget.per_source_purpose_chains_dfs.values() if p in d]
            if frames:
                merged = pd.concat(frames).groupby('pattern', as_index=False)['frequency'].sum()
                merged['probability'] = merged['frequency'] / merged['frequency'].sum()
                merged['is_valid'] = True
                budget.purpose_chains_dfs[p] = merged

    _log_budget(budget, purposes)
    return budget


def _log_budget(b: DemandBudget, purposes: List[str]) -> None:
    logger.info("=" * 70)
    logger.info("DEMAND BUDGET (person-first)")
    logger.info("=" * 70)
    for seg, d in b.segment_probs.items():
        logger.info(f"  {seg:16s} persons {b.segment_population.get(seg, 0):>12,.0f} | "
                    f"commute {d['commute']:.1%}  other travel {d['other_travel']:.1%}  "
                    f"no travel {d['no_travel']:.1%}")
    logger.info(f"  {B.SEG_CHILD:16s} persons {b.segment_population.get(B.SEG_CHILD, 0):>12,.0f} "
                f"(no own plan) | age split: {b.age_source}")
    logger.info(f"  P(commute) of workers: {b.p_commute:.1%}")
    for p in purposes:
        logger.info(f"  {p:10s} unscaled persons {b.purpose_origin_totals.get(p, 0):>12,.0f} "
                    f"(knob factor {b.purpose_factors.get(p, 1.0):.3f}, "
                    f"{len(b.purpose_chains_dfs.get(p, [])):,} chain patterns)")
    for n in b.notes:
        logger.info(f"  NOTE: {n}")
    logger.info("=" * 70)


def write_budget_json(budget: DemandBudget, path: Path, extra: Optional[Dict] = None) -> None:
    data = budget.summary()
    if extra:
        data.update(extra)
    Path(path).write_text(json.dumps(data, indent=2))
