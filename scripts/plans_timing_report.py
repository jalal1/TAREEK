"""Timing report for a generated plans.xml, without running MATSim.

Reads plans.xml directly and rebuilds the clock that the plan implies: the
first activity's end_time, then for each leg a travel time, then each
activity's max_dur. That is the schedule the generator handed to MATSim, and
MATSim's iteration 0 executes it as written.

Reports:
  1. attribute combinations (end_time / max_dur / none) per activity type
     and chain position
  2. nominal chain-end hour, overall, by chain length and by sequence
  3. nominal departures and arrivals per hour, by activity type
  4. activity duration stats per type
With --config, the same numbers for the survey person-days the generator
learns from, so each plan-side table has a target beside it.
With --legs (MATSim ITERS/it.0/0.legs.csv.gz), the simulated chain end per
person, to check the nominal clock against what MATSim actually did.

Travel time per leg is the survey mean for the (origin, destination) pair
when --config is given -- the same number _assign_times() uses for its time
budget -- else a constant --leg-minutes.

Usage:
  python scripts/plans_timing_report.py experiments/X/plans.xml \
      --config experiments/X/config_used.json \
      --legs experiments/X/output/ITERS/it.0/0.legs.csv.gz
"""

import argparse
import gzip
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HOUR_CAP = 30  # hours >= this are pooled into the last bin


def hms_to_min(s):
    h, m, sec = s.split(':')
    return int(h) * 60 + int(m) + int(sec) / 60.0


def read_plans(path):
    """Yield (person_id, [activity dict], [leg mode]) for each selected plan."""
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rb') as fh:
        pid, acts, legs, in_sel = None, [], [], False
        for event, el in ET.iterparse(fh, events=('start', 'end')):
            tag = el.tag
            if event == 'start':
                if tag == 'person':
                    pid, acts, legs = el.get('id'), [], []
                elif tag == 'plan':
                    in_sel = el.get('selected', 'yes') == 'yes'
                continue
            if tag == 'activity' and in_sel:
                acts.append({'type': el.get('type'),
                             'end_time': el.get('end_time'),
                             'max_dur': el.get('max_dur')})
            elif tag == 'leg' and in_sel:
                legs.append(el.get('mode'))
            elif tag == 'plan':
                in_sel = False
            elif tag == 'person':
                yield pid, acts, legs
                el.clear()


def hour_table(values, weights=None):
    v = np.minimum(np.floor(np.asarray(values, float) / 60.0), HOUR_CAP)
    w = np.ones_like(v) if weights is None else np.asarray(weights, float)
    s = pd.Series(w).groupby(v).sum()
    return (s / s.sum() * 100).reindex(range(0, HOUR_CAP + 1), fill_value=0.0)


def wq(values, weights, q):
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    order = np.argsort(values)
    cw = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cw, q * cw[-1])])


def section(title):
    print()
    print('=' * 78)
    print(title)
    print('=' * 78)


# --------------------------------------------------------------------------
# Plan side
# --------------------------------------------------------------------------

def build_plan_frames(plans_path, travel):
    attr_counts = Counter()
    people, events, durs = [], [], []
    for pid, acts, legs in read_plans(plans_path):
        n = len(acts)
        for i, a in enumerate(acts):
            pos = 'first' if i == 0 else ('last' if i == n - 1 else 'middle')
            key = ('end_time' if a['end_time'] else '') + \
                  ('+' if a['end_time'] and a['max_dur'] else '') + \
                  ('max_dur' if a['max_dur'] else '')
            attr_counts[(a['type'], pos, key or 'none')] += 1
        if n < 2 or not acts[0]['end_time']:
            continue
        t = hms_to_min(acts[0]['end_time'])
        start = t
        seq = [a['type'] for a in acts]
        events.append((pid, 'dep', acts[0]['type'], t, 0))
        dwell_total = 0.0
        for i in range(1, n):
            t += travel(seq[i - 1], seq[i])
            events.append((pid, 'arr', seq[i], t, i - 1))
            if i == n - 1:
                break
            a = acts[i]
            if a['max_dur']:
                d = hms_to_min(a['max_dur'])
            elif a['end_time']:
                d = max(0.0, hms_to_min(a['end_time']) - t)
            else:
                d = 0.0
            durs.append((a['type'], d))
            dwell_total += d
            t += d
            events.append((pid, 'dep', seq[i], t, i))
        people.append({'pid': pid, 'seq': '-'.join(seq), 'n_acts': n,
                       'start': start, 'end': t, 'dwell': dwell_total,
                       'has_work': 'Work' in seq[1:-1],
                       'mid_home': sum(1 for s in seq[1:-1] if s == 'Home')})
    return (attr_counts, pd.DataFrame(people),
            pd.DataFrame(events, columns=['pid', 'kind', 'act', 't', 'leg_idx']),
            pd.DataFrame(durs, columns=['act', 'dur']))


# --------------------------------------------------------------------------
# Survey side
# --------------------------------------------------------------------------

def load_survey(config):
    from data_sources.survey_manager import SurveyManager
    from data_sources.base_survey_trip import BaseSurveyTrip as B
    df = SurveyManager(config).get_survey_df().copy()
    df = df.dropna(subset=[B.DEPART_TIME, B.ARRIVE_TIME])
    df['date'] = df[B.DEPART_TIME].dt.date
    df = df.sort_values([B.PERSON_ID, 'date', B.DEPART_TIME])
    midnight = df.groupby([B.PERSON_ID, 'date'])[B.DEPART_TIME].transform('min').dt.normalize()
    df['dep_m'] = (df[B.DEPART_TIME] - midnight).dt.total_seconds() / 60.0
    df['arr_m'] = (df[B.ARRIVE_TIME] - midnight).dt.total_seconds() / 60.0
    w = df[B.TRIP_WEIGHT] if B.TRIP_WEIGHT in df.columns else 1.0
    df['w'] = pd.to_numeric(w, errors='coerce').fillna(1.0).clip(lower=1e-9)
    g = df.groupby([B.PERSON_ID, 'date'], sort=False)
    df['next_dep'] = g['dep_m'].shift(-1)
    df['dwell'] = df['next_dep'] - df['arr_m']
    days = g.agg(first_o=(B.ORIGIN_PURPOSE, 'first'),
                 dests=(B.DESTINATION_PURPOSE, list),
                 start=('dep_m', 'first'), end=('arr_m', 'last'),
                 w=('w', 'first')).reset_index()
    days['seq'] = [ '-'.join([o] + d) for o, d in zip(days.first_o, days.dests)]
    days['n_acts'] = days.dests.str.len() + 1
    mid = [d[:-1] for d in days.dests]
    days['has_work'] = [B.ACT_WORK in m for m in mid]
    days['mid_home'] = [sum(1 for x in m if x == B.ACT_HOME) for m in mid]
    days['work_n'] = [sum(1 for x in m if x == B.ACT_WORK) for m in mid]
    days['hwh'] = (days.first_o == B.ACT_HOME) & \
                  (days.dests.str[-1] == B.ACT_HOME) & (days.n_acts >= 3)
    dw = df.groupby([B.PERSON_ID, 'date'])['dwell'].sum(min_count=1).reset_index(name='dwell')
    days = days.merge(dw, on=[B.PERSON_ID, 'date'])
    return df, days


def survey_travel_fn(config, df):
    from models.time import TripDurationModel
    import logging
    logging.disable(logging.WARNING)
    tm = TripDurationModel(df, config=config)
    logging.disable(logging.NOTSET)
    return tm.mean_trip_duration


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def chain_end_block(label, ends, weights=None):
    h = hour_table(ends, weights)
    late = lambda x: h.loc[x:].sum()
    print(f"  {label:<28s} >=18h {late(18):5.1f}%  >=21h {late(21):5.1f}%  "
          f">=22h {late(22):5.1f}%  >=24h {late(24):5.1f}%")
    return h


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('plans')
    ap.add_argument('--config', help='config_used.json; enables survey comparison')
    ap.add_argument('--legs', help='MATSim it.0 legs.csv.gz; enables simulated check')
    ap.add_argument('--leg-minutes', type=float, default=20.0,
                    help='constant travel time per leg when --config is absent')
    ap.add_argument('--top', type=int, default=15, help='sequences to list')
    args = ap.parse_args()

    config = sdf = sdays = None
    travel = lambda o, d: args.leg_minutes
    travel_label = f'constant {args.leg_minutes:.0f} min/leg'
    if args.config:
        with open(args.config) as fh:
            config = json.load(fh)
        sdf, sdays = load_survey(config)
        travel = survey_travel_fn(config, sdf)
        travel_label = 'survey mean per (origin, destination) pair'

    attr, people, ev, durs = build_plan_frames(args.plans, travel)
    print(f"plans: {args.plans}")
    print(f"persons with a timed chain: {len(people):,}   legs: {(ev.kind == 'arr').sum():,}"
          f"   ({(ev.kind == 'arr').sum() / len(people):.2f} per person)")
    print(f"travel time per leg: {travel_label}")

    # 1 ------------------------------------------------------------------
    section('1. Activity attributes (type x chain position x attributes)')
    tot = Counter()
    for (t, pos, key), c in attr.items():
        tot[key] += c
    for key, c in tot.most_common():
        print(f"  {key:<18s} {c:>9,}")
    print()
    rows = sorted(attr.items(), key=lambda kv: (kv[0][1], -kv[1]))
    for (t, pos, key), c in rows:
        print(f"  {pos:<7s} {t:<10s} {key:<18s} {c:>9,}")

    # 2 ------------------------------------------------------------------
    section('2. Nominal chain end (arrival at last activity)')
    ph = chain_end_block('plans, all', people.end)
    # Segments: a work chain has Work between the first and last activity.
    # The survey side keeps Home-to-Home days only, as the generator does.
    segments = [('work', people[people.has_work], None),
                ('nonwork', people[~people.has_work], None)]
    if sdays is not None:
        max_work = config.get('chains', {}).get('max_work_activities', 2)
        segments = [('work', people[people.has_work],
                     sdays[sdays.hwh & sdays.work_n.between(1, max_work)]),
                    ('nonwork', people[~people.has_work],
                     sdays[sdays.hwh & ~sdays.has_work])]
    tables = {}
    for name, p, s in segments:
        tables[name] = (chain_end_block(f'plans, {name} chains', p.end),
                        None if s is None else chain_end_block(f'survey, {name} H..H days', s.end, s.w))
    print()
    print('  hour' + ''.join(f'  plans-{n}%  survey-{n}%' for n, _, _ in segments))
    for hr in range(4, HOUR_CAP + 1):
        line = f"  {hr:>4d}"
        for n, _, s in segments:
            ptab, stab = tables[n]
            line += f"  {ptab[hr]:10.2f}" + (f"  {stab[hr]:11.2f}" if stab is not None else '')
        print(line + ('  (and later)' if hr == HOUR_CAP else ''))

    for name, p, s in segments:
        print(f"\n  [{name}] plans {len(p) / len(people) * 100:.1f}% of persons: "
              f"mean first departure {p.start.mean() / 60:.2f}h, "
              f"mean total dwell {p.dwell.mean() / 60:.2f}h, mean end {p.end.mean() / 60:.2f}h, "
              f"mean activities {p.n_acts.mean():.2f}")
        if s is not None:
            print(f"  [{name}] survey {len(s):,} days: mean first departure "
                  f"{np.average(s.start, weights=s.w) / 60:.2f}h, "
                  f"mean total dwell {np.average(s.dwell.fillna(0), weights=s.w) / 60:.2f}h, "
                  f"mean end {np.average(s.end, weights=s.w) / 60:.2f}h, "
                  f"mean activities {np.average(s.n_acts, weights=s.w):.2f}")
        print(f"  By number of activities ({name}: plans | survey):")
        print(f"  {'n':>3s} {'share':>7s} {'start':>6s} {'dwell':>6s} {'end':>6s} {'>=22h':>6s}"
              + ('   | share  start  dwell   end  >=22h' if s is not None else ''))
        for n, g in p.groupby(np.minimum(p.n_acts, 10)):
            line = (f"  {n:>2d}{'+' if n == 10 else ' '} {len(g) / len(p) * 100:6.1f}% "
                    f"{g.start.mean() / 60:6.2f} {g.dwell.mean() / 60:6.2f} {g.end.mean() / 60:6.2f} "
                    f"{(g.end >= 1320).mean() * 100:5.1f}%")
            if s is not None:
                ss = s[np.minimum(s.n_acts, 10) == n]
                if len(ss):
                    line += (f"   | {ss.w.sum() / s.w.sum() * 100:4.1f}% "
                             f"{np.average(ss.start, weights=ss.w) / 60:6.2f} "
                             f"{np.average(ss.dwell.fillna(0), weights=ss.w) / 60:6.2f} "
                             f"{np.average(ss.end, weights=ss.w) / 60:5.2f} "
                             f"{ss.w[ss.end >= 1320].sum() / ss.w.sum() * 100:5.1f}%")
            print(line)
    sw = segments[0][2]

    print('\n  By tour structure (mid-chain Home returns):')
    for k, g in people.groupby(np.minimum(people.mid_home, 3)):
        print(f"  mid-Home={k}{'+' if k == 3 else ' '} {len(g) / len(people) * 100:5.1f}%  "
              f"mean end {g.end.mean() / 60:5.2f}h  >=22h {(g.end >= 1320).mean() * 100:5.1f}%")

    for name, p, s in segments:
        print(f'\n  Top {args.top} {name} sequences (share within segment; plans | survey):')
        for seq, c in p.seq.value_counts().head(args.top).items():
            g = p[p.seq == seq]
            line = (f"  {c / len(p) * 100:5.1f}% start {g.start.mean() / 60:5.2f} "
                    f"end {g.end.mean() / 60:5.2f} >=22h {(g.end >= 1320).mean() * 100:5.1f}%")
            if s is not None:
                ss = s[s.seq == seq]
                if len(ss):
                    line += (f"  | {ss.w.sum() / s.w.sum() * 100:5.1f}% "
                             f"start {np.average(ss.start, weights=ss.w) / 60:5.2f} "
                             f"end {np.average(ss.end, weights=ss.w) / 60:5.2f}")
                else:
                    line += '  |  (not in survey)          '
            print(line + f"  {seq}")

    if sdf is not None:
        # _assign_times() samples the first departure from the KDE of ALL
        # survey trips with the same (origin, destination) pair, wherever
        # they fall in the day. Compare that with the first trips only.
        print('\n  First departure: survey KDE pool (all trips of the pair) vs '
              'first trips of the day only (weighted mean hour, n):')
        first = sdf.groupby(['person_id', 'date']).head(1)
        for (o, d), g in sdf.groupby(['origin_purpose', 'destination_purpose']):
            if o != 'Home' or len(g) < 100:
                continue
            f = first[(first.origin_purpose == o) & (first.destination_purpose == d)]
            if len(f) == 0:
                continue
            print(f"  {o}->{d:<9s} all {np.average(g.dep_m, weights=g.w) / 60:5.2f}h (n={len(g):>5,})"
                  f"   first-of-day {np.average(f.dep_m, weights=f.w) / 60:5.2f}h (n={len(f):>5,})")

    # 3 ------------------------------------------------------------------
    section('3. Nominal departures / arrivals per hour, by activity type (% of all)')
    for kind, label in (('dep', 'departures, by activity LEFT'),
                        ('arr', 'arrivals, by activity REACHED')):
        e = ev[ev.kind == kind]
        hrs = np.minimum(np.floor(e.t / 60), HOUR_CAP).astype(int)
        tab = pd.crosstab(hrs, e.act) / len(e) * 100
        tab['ALL'] = tab.sum(axis=1)
        print(f"\n  {label}")
        with pd.option_context('display.width', 200, 'display.max_columns', 20):
            print(tab.round(2).to_string())
    dep = ev[ev.kind == 'dep']
    late = dep[dep.t >= 1320]
    print(f"\n  departures at/after 22h: {len(late):,} of {len(dep):,}; "
          f"leg index: first={int((late.leg_idx == 0).sum()):,}, "
          f">=5th={int((late.leg_idx >= 4).sum()):,}")
    if sdf is not None:
        s_dep_h = hour_table(sdf.dep_m, sdf.w)
        p_dep_h = hour_table(dep.t)
        print('\n  all departures per hour, plans% vs survey%:')
        for hr in range(4, HOUR_CAP + 1):
            print(f"  {hr:>4d}  {p_dep_h[hr]:6.2f}  {s_dep_h[hr]:6.2f}")

    # 4 ------------------------------------------------------------------
    section('4. Activity durations (min): plans max_dur vs survey dwell')
    print(f"  {'act':<10s} {'n':>8s} {'mean':>6s} {'p50':>6s} {'p90':>6s}"
          + ('  | survey n   mean    p50    p90' if sdf is not None else ''))
    s_dw = None
    if sdf is not None:
        s_dw = sdf.dropna(subset=['dwell'])
        s_dw = s_dw[s_dw.dwell > 0]
        cons = config.get('duration_constraints', {}).get('activity_durations', {})
        lo = s_dw.destination_purpose.map(lambda a: cons.get(a, {}).get('min_minutes', 1))
        hi = s_dw.destination_purpose.map(lambda a: cons.get(a, {}).get('max_minutes', 720))
        s_dw = s_dw[(s_dw.dwell >= lo) & (s_dw.dwell <= hi)]
    for act, g in durs.groupby('act'):
        line = (f"  {act:<10s} {len(g):>8,} {g.dur.mean():6.0f} {g.dur.median():6.0f} "
                f"{g.dur.quantile(.9):6.0f}")
        if s_dw is not None:
            s = s_dw[s_dw.destination_purpose == act]
            if len(s):
                line += (f"  | {len(s):>7,} {np.average(s.dwell, weights=s.w):6.0f} "
                         f"{wq(s.dwell, s.w, .5):6.0f} {wq(s.dwell, s.w, .9):6.0f}")
        print(line)

    # 5 ------------------------------------------------------------------
    if args.legs:
        section('5. Check against MATSim it.0 (simulated arrival at last activity)')
        legs = pd.read_csv(args.legs, sep=';', usecols=['person', 'dep_time', 'trav_time'])
        for c in ('dep_time', 'trav_time'):
            legs[c] = legs[c].map(hms_to_min)
        legs['arr'] = legs.dep_time + legs.trav_time
        sim_end = legs.groupby('person').arr.max()
        m = people.set_index('pid').end.to_frame('nominal').join(sim_end.rename('sim'), how='inner')
        print(f"  persons matched: {len(m):,}")
        # Dwell = next departure - this arrival, per person, in leg order.
        # This does not depend on congestion, so it shows whether MATSim
        # executes max_dur as written.
        legs = legs.sort_values(['person', 'dep_time'])
        legs['next_dep'] = legs.groupby('person').dep_time.shift(-1)
        sim_dwell = (legs.next_dep - legs.arr).dropna()
        plan_dwell = durs.dur.to_numpy()
        print(f"  dwell per mid-chain activity: plans median {np.median(plan_dwell):.1f} min, "
              f"it.0 median {sim_dwell.median():.1f} min, mean {plan_dwell.mean():.1f} vs {sim_dwell.mean():.1f}")
        print("  NOTE: it.0 carries the untrained, congested first iteration. Travel times in the"
              " tail are not demand; read the medians, not the hour table below.")
        print(f"  mean end: nominal {m.nominal.mean() / 60:.2f}h, simulated {m.sim.mean() / 60:.2f}h; "
              f"median diff (sim-nominal) {(m.sim - m.nominal).median():.1f} min, "
              f"p10/p90 {(m.sim - m.nominal).quantile(.1):.0f}/{(m.sim - m.nominal).quantile(.9):.0f} min")
        hn, hs = hour_table(m.nominal), hour_table(m.sim)
        print('  hour  nominal%  simulated%')
        for hr in range(16, HOUR_CAP + 1):
            print(f"  {hr:>4d}  {hn[hr]:7.2f}  {hs[hr]:9.2f}")


if __name__ == '__main__':
    main()
