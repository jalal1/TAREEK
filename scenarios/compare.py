# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare a scenario run with its baseline, link by link.

Writes into the scenario folder:
  link_changes.csv      one row per car link: volumes before/after, change
  compare_report.md     the report source
  compare_report.html   the report, in the style of report.html
  compare/              the figures

Volumes are the final linkstats of each run (averaged over the iterations
linkStats.averageLinkStatsOverIterations sets), scaled by 1/flowCapacityFactor
the same way the evaluator scales them. Both runs have the same link IDs: a
closed link stays in the network with 'car' removed. See scenarios/README.md.
"""

import gzip
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scenarios.definition import ScenarioError
from scenarios.network import CAR, read_network
from scenarios.run import network_file_name, read_summary
from utils.logger import setup_logger

logger = setup_logger(__name__)

HOURS = range(24)
VOL_COLS = [f'HRS{h}-{h + 1}avg' for h in HOURS]
TT_COLS = [f'TRAVELTIME{h}-{h + 1}avg' for h in HOURS]
# A link is "low volume" when both runs put fewer simulated (unscaled)
# vehicles than this on it in a day. Its change is mostly random variation.
LOW_VOLUME_SIM_VEHICLES = 50
TOP_ROADS = 15
# A road's link counts toward 'Km affected' when its change is at least this
# share of the road's biggest change.
ROAD_SPREAD = 0.2
# Links with the same name (or, with no name, the same road type) belong to one
# road when they share a node or come this close, in metres: the two sides of
# a divided road share no node. Farther apart, they are different roads, such
# as a '3rd Street' in two towns.
SAME_ROAD_GAP_M = 300.0
# A road that needs a place in its label is named after the biggest other
# named road within this distance of its biggest change: '(no name), near X'.
LOCATOR_RADIUS_M = 1500.0
LOCATOR_RANK = {'motorway': 0, 'trunk': 1, 'primary': 2, 'secondary': 3, 'tertiary': 4}
ROUNDABOUT = '(roundabout)'
MAX_STATION_ROWS = 40
# Context kept around the closure in the zoomed map, in metres.
ZOOM_MARGIN_M = 5000.0
# A map's colour scale is set by the links that change by at least this share
# of the map's biggest change (see _color_limit).
MAP_SCALE_FLOOR = 0.05


def _flow_factor(exp_dir: Path) -> float:
    from matsim.evaluator import SimulationEvaluator
    flow, _ = SimulationEvaluator(exp_dir).load_scaling_factors()
    return flow


def load_linkstats(exp_dir: Path) -> Tuple[pd.DataFrame, Path]:
    """Hourly volumes (unscaled) and travel times of the run's last linkstats."""
    from matsim.evaluator import SimulationEvaluator
    path = SimulationEvaluator(exp_dir).find_linkstats_file()
    if path is None:
        raise ScenarioError(f"No linkstats in {exp_dir / 'output' / 'ITERS'}: "
                            "has the run finished?")
    with gzip.open(path, 'rt') as f:
        df = pd.read_csv(f, sep='\t', usecols=['LINK'] + VOL_COLS + TT_COLS,
                         dtype={'LINK': str})
    return df.rename(columns={'LINK': 'link_id'}).set_index('link_id'), path


def build_link_changes(base_dir: Path, run_dir: Path) -> Tuple[pd.DataFrame, Dict]:
    """The per-link table and the run facts the report needs."""
    summary = read_summary(run_dir)
    flow_base, flow_run = _flow_factor(base_dir), _flow_factor(run_dir)
    if abs(flow_base - flow_run) > 1e-9:
        raise ScenarioError(f"The runs use different samples (flowCapacityFactor "
                            f"{flow_base} vs {flow_run}); they cannot be compared.")
    scale = 1.0 / flow_base if 0 < flow_base < 1 else 1.0

    links, nodes = read_network(base_dir / network_file_name(base_dir / 'config.xml'))
    before, before_path = load_linkstats(base_dir)
    after, after_path = load_linkstats(run_dir)

    car_ids = [l for l, info in links.items() if CAR in info.modes]
    selected = set(summary['closed_links']['selected'])
    cut_off = set(summary['closed_links']['cut_off'])

    vb = before.reindex(car_ids)[VOL_COLS].fillna(0.0).to_numpy()
    va = after.reindex(car_ids)[VOL_COLS].fillna(0.0).to_numpy()
    tb = before.reindex(car_ids)[TT_COLS].to_numpy()
    ta = after.reindex(car_ids)[TT_COLS].to_numpy()

    info = [links[l] for l in car_ids]
    df = pd.DataFrame({
        'link_id': car_ids,
        'name': [i.name for i in info],
        'road_type': [i.highway for i in info],
        'length_m': [round(i.length, 1) for i in info],
        'lanes': [i.lanes for i in info],
        'capacity_veh_h': [i.capacity for i in info],
        'closed': ['selected' if l in selected else 'cut_off' if l in cut_off else ''
                   for l in car_ids],
    })
    daily_b_sim, daily_a_sim = vb.sum(axis=1), va.sum(axis=1)
    df['daily_before'] = np.round(daily_b_sim * scale, 1)
    df['daily_after'] = np.round(daily_a_sim * scale, 1)
    df['change'] = np.round(df['daily_after'] - df['daily_before'], 1)
    with np.errstate(divide='ignore', invalid='ignore'):
        pct = np.where(df['daily_before'] > 0,
                       100.0 * df['change'] / df['daily_before'], np.nan)
    df['change_pct'] = np.round(pct, 1)
    df['low_volume'] = np.maximum(daily_b_sim, daily_a_sim) < LOW_VOLUME_SIM_VEHICLES
    hourly = np.round((va - vb) * scale, 1)
    for h in HOURS:
        df[f'change_h{h:02d}'] = hourly[:, h]

    lengths = np.array([i.length for i in info])[:, None]
    freespeed = np.array([i.freespeed if i.freespeed > 0 else np.nan for i in info])[:, None]
    free_tt = lengths / freespeed

    def totals(vol: np.ndarray, tt: np.ndarray) -> Dict[str, float]:
        vol = vol * scale
        tt = np.where(np.isfinite(tt), tt, free_tt)
        vht = np.nansum(vol * tt) / 3600.0
        delay = np.nansum(vol * np.clip(tt - free_tt, 0, None)) / 3600.0
        return {
            'vehicle_km': float(np.nansum(vol * lengths) / 1000.0),
            'vehicle_hours': float(vht),
            'delay_hours': float(delay),
        }

    facts = {
        'summary': summary,
        'scale': scale,
        'flow_factor': flow_base,
        'before_linkstats': str(before_path),
        'after_linkstats': str(after_path),
        'totals_before': totals(vb, tb),
        'totals_after': totals(va, ta),
        'links': links,
        'nodes': nodes,
        'roads': road_geometry(df, links, nodes),
    }
    return df, facts


def road_geometry(df: pd.DataFrame, links, nodes) -> pd.DataFrame:
    """Group the links of df into roads; add each link's direction and midpoint.

    A road is the links with the same name that share a node or are within
    SAME_ROAD_GAP_M of each other. Links with no name are grouped the same way
    by road type, so a stretch of unnamed freeway is one road. Returns a frame
    with df's index: road (an integer ID), dx, dy (link vector), mx, my
    (midpoint), roundabout (OSM junction=roundabout).
    """
    ids = df['link_id'].tolist()
    names = df['name'].fillna('').astype(str).tolist()
    types = df['road_type'].fillna('').astype(str).tolist()
    # An unnamed roundabout is one road (its ring), whatever the types of its
    # links. It is joined by shared nodes only: roundabouts in a row are often
    # closer than the gap.
    rings = [links[l].junction == 'roundabout' for l in ids]
    keys = [(True, n) if n else (False, ROUNDABOUT if ring else t)
            for n, t, ring in zip(names, types, rings)]
    nan = (np.nan, np.nan)
    a = np.array([nodes.get(links[l].from_node, nan) for l in ids], dtype=float).reshape(-1, 2)
    b = np.array([nodes.get(links[l].to_node, nan) for l in ids], dtype=float).reshape(-1, 2)

    parent = list(range(len(ids)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    first = {}
    for i, link_id in enumerate(ids):
        info = links[link_id]
        for node in (info.from_node, info.to_node):
            union(first.setdefault((keys[i], node), i), i)

    # Join pieces closer than the gap. Each node goes in a grid cell of the gap
    # size, so only nodes in the same or a neighbouring cell are compared.
    gap = SAME_ROAD_GAP_M
    cells = defaultdict(list)
    for i in range(len(ids)):
        if keys[i] == (False, ROUNDABOUT):
            continue
        for x, y in (a[i], b[i]):
            if np.isfinite(x) and np.isfinite(y):
                cells[(keys[i], int(x // gap), int(y // gap))].append((i, x, y))
    for (key, cx, cy), members in cells.items():
        for ox, oy in ((0, 0), (1, -1), (1, 0), (1, 1), (0, 1)):
            others = members if (ox, oy) == (0, 0) else cells.get((key, cx + ox, cy + oy))
            if not others:
                continue
            for i, x, y in members:
                for j, u, v in others:
                    if find(i) != find(j) and (x - u) ** 2 + (y - v) ** 2 <= gap * gap:
                        union(i, j)

    roots = [find(i) for i in range(len(ids))]
    _, road = np.unique(roots, return_inverse=True)
    return pd.DataFrame({
        'road': road,
        'dx': b[:, 0] - a[:, 0], 'dy': b[:, 1] - a[:, 1],
        'mx': (a[:, 0] + b[:, 0]) / 2, 'my': (a[:, 1] + b[:, 1]) / 2,
        'roundabout': rings,
    }, index=df.index)


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def _segments(df: pd.DataFrame, links, nodes) -> np.ndarray:
    seg = []
    for link_id in df['link_id']:
        info = links[link_id]
        a, b = nodes.get(info.from_node), nodes.get(info.to_node)
        seg.append([a or (np.nan, np.nan), b or (np.nan, np.nan)])
    return np.array(seg, dtype=float)


def _color_limit(change: np.ndarray) -> float:
    """The end of a map's colour scale, in vehicles per day.

    Most links in a map change a little, so a percentile of all of them sits
    far below the diversion routes, and every diversion route then has the
    same full colour. The percentile is taken over the links whose change is
    at least MAP_SCALE_FLOOR of the biggest change in the map.
    """
    values = np.abs(change[np.isfinite(change)])
    if not values.size:
        return 1.0
    big = values[values >= MAP_SCALE_FLOOR * values.max()]
    return max(float(np.percentile(big, 98)), 1.0)


def plot_change_maps(df: pd.DataFrame, facts: Dict, out_dir: Path) -> List[Tuple[str, str]]:
    """Whole region, and zoomed to the closure. Red = more traffic, blue = less."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import TwoSlopeNorm

    out_dir.mkdir(parents=True, exist_ok=True)
    links, nodes = facts['links'], facts['nodes']
    seg_all = _segments(df, links, nodes)
    closed_mask = (df['closed'] != '').to_numpy()
    change = df['change'].to_numpy()
    shown = (~closed_mask) & (~df['low_volume'].to_numpy()) & (np.abs(change) > 0)

    mid = np.nanmean(seg_all, axis=1)

    closed_seg = seg_all[closed_mask]
    cx = closed_seg[:, :, 0][np.isfinite(closed_seg[:, :, 0])]
    cy = closed_seg[:, :, 1][np.isfinite(closed_seg[:, :, 1])]

    figures = []
    views = [('volume_change_region.png', 'Whole region', None)]
    if cx.size:
        views.append(('volume_change_closure.png', 'Around the closure',
                      (cx.min() - ZOOM_MARGIN_M, cx.max() + ZOOM_MARGIN_M,
                       cy.min() - ZOOM_MARGIN_M, cy.max() + ZOOM_MARGIN_M)))

    order = np.argsort(np.abs(change[shown]))  # big changes drawn on top
    for fname, title, box in views:
        if box is None:
            xs, ys = seg_all[:, :, 0], seg_all[:, :, 1]
            box = (np.nanmin(xs), np.nanmax(xs), np.nanmin(ys), np.nanmax(ys))
        # Size the figure to the map's shape, so a wide area is not drawn in
        # a square with empty bands above and below.
        ratio = (box[3] - box[2]) / max(box[1] - box[0], 1.0)
        in_box = ((mid[:, 0] >= box[0]) & (mid[:, 0] <= box[1])
                  & (mid[:, 1] >= box[2]) & (mid[:, 1] <= box[3]))
        limit = _color_limit(change[shown & in_box])
        norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
        fig, ax = plt.subplots(figsize=(11, float(np.clip(9 * ratio, 4, 12))))
        ax.add_collection(LineCollection(seg_all, colors='#d0d0d0', linewidths=0.3, zorder=1))
        seg_c, val_c = seg_all[shown][order], change[shown][order]
        width = 0.6 + 3.0 * np.clip(np.abs(val_c) / limit, 0, 1)
        lc = LineCollection(seg_c, cmap='RdBu_r', norm=norm, linewidths=width, zorder=2)
        lc.set_array(val_c)
        ax.add_collection(lc)
        ax.add_collection(LineCollection(closed_seg, colors='black', linewidths=2.5,
                                         linestyles='dotted', zorder=3))
        ax.set_xlim(box[0], box[1])
        ax.set_ylim(box[2], box[3])
        ax.set_aspect('equal')
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"Daily volume change, {title.lower()} "
                     f"(black dots = closed)", fontsize=12)
        cbar = fig.colorbar(lc, ax=ax, shrink=0.6, extend='both')
        cbar.set_label('Vehicles per day (scenario - baseline)')
        fig.tight_layout()
        fig.savefig(out_dir / fname, dpi=150)
        plt.close(fig)
        figures.append((f"compare/{fname}", title))
    return figures


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def _fmt(value, decimals: int = 0) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return '–'
    return f"{value:,.{decimals}f}"


def _road_km(links: pd.DataFrame, geo: pd.DataFrame) -> float:
    """Length of a road's links in km, one direction counted.

    Each direction of a road is its own link, and a divided road has two sides.
    The links are split by direction along the road's main axis (the
    length-weighted mean of the link bearings, taken modulo 180 degrees), and
    the longer direction is the road's length. A ramp (one direction) counts
    in full.
    """
    g = geo.loc[links.index]
    w = links['length_m'].to_numpy(dtype=float)
    theta = np.arctan2(g['dy'].to_numpy(), g['dx'].to_numpy())
    axis = 0.5 * np.arctan2(np.nansum(w * np.sin(2 * theta)), np.nansum(w * np.cos(2 * theta)))
    forward = np.cos(theta - axis) >= 0
    return max(w[forward].sum(), w[~forward].sum()) / 1000.0


def _locator(df: pd.DataFrame, geo: pd.DataFrame, link_index, own_name: str,
             count: int = 1) -> str:
    """Named roads near a link, to tell a road's place.

    The first is the biggest road within LOCATOR_RADIUS_M (by type, motorway
    first, then by distance); with none that close, the nearest named road.
    With count=2, the second is the nearest other named road: for a ramp or a
    roundabout, usually the cross street at that place.
    """
    x, y = geo.at[link_index, 'mx'], geo.at[link_index, 'my']
    named = df['name'].fillna('').astype(str)
    candidates = (named != '') & (named != own_name)
    if not candidates.any() or not np.isfinite(x):
        return ''
    d2 = (geo['mx'] - x) ** 2 + (geo['my'] - y) ** 2
    near = candidates & (d2 <= LOCATOR_RADIUS_M ** 2)
    if not near.any():
        return named[d2[candidates].idxmin()]
    order = pd.DataFrame({
        'name': named[near],
        'rank': df.loc[near, 'road_type'].map(LOCATOR_RANK).fillna(len(LOCATOR_RANK)),
        'd2': d2[near],
    }).sort_values(['rank', 'd2'])
    first = order['name'].iloc[0]
    rest = order.sort_values('d2')['name']
    return ' and '.join([first] + rest[rest != first].drop_duplicates().head(count - 1).tolist())


def _road_label(df: pd.DataFrame, geo: pd.DataFrame, link_index) -> str:
    """The name of a link's road, as the report shows it.

    A name that only one road has is used as it is. A name that several roads
    have gets the biggest nearby road; an unnamed road gets two nearby roads.
    """
    name = str(df.at[link_index, 'name'] or '')
    if name:
        names = df['name'].fillna('').astype(str)
        if geo.loc[names == name, 'road'].nunique() == 1:
            return name
    near = _locator(df, geo, link_index, name, count=1 if name else 2)
    unnamed = ROUNDABOUT if geo.at[link_index, 'roundabout'] else '(no name)'
    return f"{name or unnamed}{', near ' + near if near else ''}"


def _road_table(df: pd.DataFrame, geo: pd.DataFrame, gained: bool) -> List[str]:
    """One row per road: its biggest change and how far the change reaches.

    A road is many links, so a list of links is filled by one road. This table
    groups the links into roads (see road_geometry). 'Km affected' is the
    length of the road, one direction counted, whose change is at least
    ROAD_SPREAD of its biggest change. A road with no name, or with a name that
    other roads also have, gets a nearby road in its label.
    """
    open_links = df[(df['closed'] == '') & ~df['low_volume']]
    shown = open_links[open_links['change'] > 0] if gained else open_links[open_links['change'] < 0]
    if shown.empty:
        return ['No road ' + ('gained' if gained else 'lost') + ' traffic.']
    rows = []
    for _, grp in shown.groupby(geo.loc[shown.index, 'road']):
        peak_index = grp['change'].abs().idxmax()
        peak = grp.loc[peak_index]
        spread = grp[grp['change'].abs() >= ROAD_SPREAD * abs(peak['change'])]
        types = grp['road_type'].mode()
        rows.append({
            'peak_index': peak_index,
            'road_type': types.iloc[0] if not types.empty else '',
            'peak': peak['change'],
            'before': peak['daily_before'],
            'pct': peak['change_pct'],
            'km': _road_km(spread, geo),
            'link': peak['link_id'],
        })
    table = pd.DataFrame(rows).sort_values('peak', ascending=not gained).head(TOP_ROADS)
    table['name'] = [_road_label(df, geo, i) for i in table['peak_index']]
    lines = ['| Road | Type | Biggest change | Before (that link) | Change % | Km affected | Link |',
             '|---|---|---:|---:|---:|---:|---|']
    for _, r in table.iterrows():
        lines.append(f"| {str(r['name']).replace('|', '/')} | {r['road_type'] or '–'} | "
                     f"{_fmt(r['peak'])} | {_fmt(r['before'])} | {_fmt(r['pct'], 1)} | "
                     f"{_fmt(r['km'], 1) if r['km'] >= 0.05 else '< 0.1'} | {r['link']} |")
    return lines


def _load_countscompare(exp_dir: Path) -> Optional[pd.DataFrame]:
    """The hourly rows of the run's last countscompare.txt."""
    from matsim.evaluator import SimulationEvaluator
    path = SimulationEvaluator(exp_dir).find_countscompare_file()
    if path is None:
        return None
    return pd.read_csv(path, sep='\t', dtype={'Link Id': str, 'Count Station Id': str})


def _fit(hourly: pd.DataFrame) -> Dict[str, float]:
    """Count fit on station-hours, as the evaluator computes it.

    Correlation: Pearson r over the hours with a non-zero count. GEH < 5: share
    of hourly rows. Level: total simulated / total counted.
    """
    nonzero = hourly[hourly['Count volumes'] > 0]
    r = (nonzero[['Count volumes', 'MATSIM volumes']].corr().iloc[0, 1]
         if len(nonzero) > 1 else float('nan'))
    geh = hourly['GEH'].dropna()
    counted = hourly['Count volumes'].sum()
    return {
        'correlation': float(r),
        'geh_lt_5_pct': float(100.0 * (geh < 5).mean()) if len(geh) else float('nan'),
        'level': float(hourly['MATSIM volumes'].sum() / counted) if counted else float('nan'),
        'links': int(hourly['Link Id'].nunique()),
    }


def _count_section(base_dir: Path, run_dir: Path, df: pd.DataFrame,
                   geo: pd.DataFrame) -> List[str]:
    before, after = _load_countscompare(base_dir), _load_countscompare(run_dir)
    if before is None or after is None:
        return []
    closed_ids = set(df.loc[df['closed'] != '', 'link_id'])
    closed_counts = sorted(set(before['Link Id']) & closed_ids)

    L = ['## Count fit, before and after', '']
    if closed_counts:
        L += [f"**{len(closed_counts)} count link(s) are inside the closure.** The scenario has "
              "no traffic there, but the count is the real traffic without a closure. These "
              "links pull the fit down a lot, so the table also shows the fit without them. "
              "That is the number to read: it shows whether the closure changed the fit "
              "at the other stations.", '']
    rows = [('All count links', before, after)]
    if closed_counts:
        rows.append(('Without the closed links',
                     before[~before['Link Id'].isin(closed_ids)],
                     after[~after['Link Id'].isin(closed_ids)]))
    L += ['| Count links | Number | Correlation, baseline | Correlation, scenario | '
          'GEH < 5 %, baseline | GEH < 5 %, scenario | Level, baseline | Level, scenario |',
          '|---|---:|---:|---:|---:|---:|---:|---:|']
    for label, b, a in rows:
        fb, fa = _fit(b), _fit(a)
        L.append(f"| {label} | {fb['links']} | {_fmt(fb['correlation'], 3)} | "
                 f"{_fmt(fa['correlation'], 3)} | {_fmt(fb['geh_lt_5_pct'], 1)} | "
                 f"{_fmt(fa['geh_lt_5_pct'], 1)} | {_fmt(fb['level'], 3)} | {_fmt(fa['level'], 3)} |")
    L += ['', 'Correlation is over station-hours with a non-zero count. Level is total '
          'simulated / total counted (1.0 = right level). From countscompare.txt of the last '
          'iteration of each run.', '']

    # Daily volume per count link.
    keys = ['Count Station Id', 'Link Id']
    vols = ['MATSIM volumes', 'Count volumes']
    m = before.groupby(keys)[vols].sum().reset_index().merge(
        after.groupby(keys)[vols].sum().reset_index(), on=keys, suffixes=('_b', '_a'))
    row_of = pd.Series(df.index, index=df['link_id'])
    m['road'] = [_road_label(df, geo, row_of[l]) if l in row_of.index else '(no name)'
                 for l in m['Link Id']]
    m['closed'] = m['Link Id'].isin(closed_ids)
    m['change'] = m['MATSIM volumes_a'] - m['MATSIM volumes_b']
    m = m.sort_values(['closed', 'change'], ascending=[False, True])
    if len(m) > MAX_STATION_ROWS:
        rest = m[~m['closed']]
        rest = rest.loc[rest['change'].abs().sort_values(ascending=False).index]
        m = pd.concat([m[m['closed']], rest.head(max(MAX_STATION_ROWS - int(m['closed'].sum()), 0))])
        L += [f"### Count stations (closed links, then the {MAX_STATION_ROWS} biggest changes)", '']
    else:
        L += ['### Count stations', '']
    L += ['| Station | Link | Road | Closed | Counted | Baseline | Scenario | Change |',
          '|---|---|---|---|---:|---:|---:|---:|']
    for _, r in m.iterrows():
        L.append(f"| {r['Count Station Id']} | {r['Link Id']} | {str(r['road']).replace('|', '/')} | "
                 f"{'yes' if r['closed'] else ''} | {_fmt(r['Count volumes_b'])} | "
                 f"{_fmt(r['MATSIM volumes_b'])} | {_fmt(r['MATSIM volumes_a'])} | "
                 f"{_fmt(r['change'])} |")
    return L + ['', 'Vehicles per day.', '']


def _closure_summary(df: pd.DataFrame, s: Dict) -> List[str]:
    """What was closed, in a few lines. The link IDs are in link_changes.csv."""
    selected = df[df['closed'] == 'selected']
    cut_off = df[df['closed'] == 'cut_off']
    L = ['## What was closed', '',
         f"- **{len(selected)} selected link(s)**, {selected['length_m'].sum() / 1000:.1f} km "
         "(each direction counted). Cars and trucks cannot use them.",
         f"- The busiest of them carried **{_fmt(selected['daily_before'].max())} vehicles per "
         "day** in the baseline. That traffic must find another route."]
    if len(cut_off):
        types = ', '.join(f"{n} {t or 'other'}" for t, n in
                          cut_off['road_type'].value_counts().items())
        L.append(f"- **{len(cut_off)} more link(s)** ({cut_off['length_m'].sum() / 1000:.1f} km: "
                 f"{types}) were closed because the closure cut them off: you could drive in "
                 "but not out, or the other way. Ramps that lead only into the closed stretch "
                 "are an example.")
    on_transit = set(s['closed_links'].get('used_by_transit') or [])
    if on_transit:
        L.append(f"- {len(on_transit)} closed link(s) are on bus lines. Buses still drive "
                 "there, because a bus line is a fixed list of links.")
    L.append("- The `closed` column of `link_changes.csv` lists every closed link "
             "(`selected` or `cut_off`).")
    # Only a fault is worth a line: cars on a closed link that no bus line uses.
    leak = df[(df['closed'] != '') & ~df['link_id'].isin(on_transit) & (df['daily_after'] > 0)]
    if len(leak):
        L.append(f"- **Warning:** {len(leak)} closed link(s) still have traffic "
                 f"({_fmt(leak['daily_after'].sum())} vehicles per day). This should not happen; "
                 "check the scenario run log.")
    return L + ['']


def build_markdown(base_dir: Path, run_dir: Path, df: pd.DataFrame, facts: Dict,
                   figures: List[Tuple[str, str]]) -> str:
    s = facts['summary']
    L = [f"# Scenario comparison: {s['scenario']}", '']
    if s.get('description'):
        L += [s['description'], '']
    L += [f"Baseline `{base_dir.name}` · scenario run `{run_dir.name}` · "
          f"made {datetime.now():%Y-%m-%d %H:%M}", '']

    L += ['## How to read this report', '',
          "- The two runs have the same people, trips, settings and random seed; only the "
          "closure differs. A small random variation remains.",
          "- Volumes are vehicles per day (cars, trucks and buses together), from the last "
          f"linkstats of each run, scaled by 1/{facts['flow_factor']} = {facts['scale']:.2f} "
          "to the full population.",
          "- Each direction of a road is its own link.",
          f"- **Low volume**: fewer than {LOW_VOLUME_SIM_VEHICLES} simulated vehicles per day "
          "in both runs. Its change is mostly random variation, so it is left out of the maps "
          "and the road tables.",
          "- **Road** (in the road tables): the links with the same name that are connected, "
          f"or less than {SAME_ROAD_GAP_M:.0f} m apart (the two sides of a divided road). Roads "
          "with the same name in different places are separate rows, and their label names a "
          "nearby road. Links with no name (often freeways, ramps and roundabouts) are grouped "
          "the same way by road type, and are labelled with the two biggest nearby roads. "
          "Connected unnamed freeways can form one long row; the Link column shows where the "
          "biggest change is.",
          f"- **Km affected**: the length of a road whose change is at least "
          f"{int(ROAD_SPREAD * 100)}% of that road's biggest change. One direction is counted.",
          "- Local road volumes are not checked against counts (count stations are mostly on "
          "state highways). Read them as the likely direction and size of a change.",
          "- The full table, with the hourly changes for every link, is in `link_changes.csv`.",
          '']

    L += _closure_summary(df, s)

    tb, ta = facts['totals_before'], facts['totals_after']
    L += ['## Network totals', '',
          '| Measure | Baseline | Scenario | Change | Change % |',
          '|---|---:|---:|---:|---:|']
    for key, label in [('vehicle_km', 'Vehicle-km per day'),
                       ('vehicle_hours', 'Vehicle-hours per day'),
                       ('delay_hours', 'Delay, vehicle-hours per day')]:
        b, a = tb[key], ta[key]
        pct = 100.0 * (a - b) / b if b else float('nan')
        L.append(f"| {label} | {_fmt(b)} | {_fmt(a)} | {_fmt(a - b)} | {_fmt(pct, 2)} |")
    L += ['', 'Delay is the time above free-flow time on each link, summed over all vehicles.', '']

    if figures:
        L += ['## Maps', '',
              'Red roads gained traffic, blue roads lost traffic. Black dots are the closed '
              'links. Low-volume roads are not drawn.', '']
        for src, title in figures:
            L += [f"![{title}]({src})", '', f"*{title}*", '']

    L += [f'## Roads with the most added traffic (top {TOP_ROADS})', '']
    L += _road_table(df, facts['roads'], gained=True) + ['']
    L += [f'## Roads with the most lost traffic (top {TOP_ROADS})', '']
    L += _road_table(df, facts['roads'], gained=False) + ['']

    L += _count_section(base_dir, run_dir, df, facts['roads'])
    return '\n'.join(L)


def compare(base_dir: Path, run_dir: Path) -> Path:
    """Write link_changes.csv and compare_report.html into the scenario folder."""
    base_dir, run_dir = Path(base_dir).resolve(), Path(run_dir).resolve()
    summary = read_summary(run_dir)
    if summary.get('base_experiment') != base_dir.name:
        raise ScenarioError(f"{run_dir.name} was made from "
                            f"'{summary.get('base_experiment')}', not '{base_dir.name}'.")

    logger.info(f"Comparing {run_dir.name} with {base_dir.name}")
    df, facts = build_link_changes(base_dir, run_dir)
    csv_path = run_dir / 'link_changes.csv'
    df.to_csv(csv_path, index=False)
    logger.info(f"Wrote {csv_path} ({len(df):,} car links)")

    try:
        figures = plot_change_maps(df, facts, run_dir / 'compare')
    except Exception as e:
        logger.warning(f"Map figures failed; the report is written without them: {e}")
        figures = []

    md_text = build_markdown(base_dir, run_dir, df, facts, figures)
    (run_dir / 'compare_report.md').write_text(md_text, encoding='utf-8')

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
    from experiment_report import markdown_to_html
    html_text = markdown_to_html(md_text, f"Scenario {summary['scenario']}", base_dir=run_dir)
    html_path = run_dir / 'compare_report.html'
    html_path.write_text(html_text, encoding='utf-8')
    logger.info(f"Wrote {html_path}")
    return html_path
