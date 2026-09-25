"""Trip timing and activity duration figures: generated demand vs simulation.

Five figures, written to the evaluation directory:

- ``dep_arr_by_activity_demand.png`` / ``dep_arr_by_activity_sim.png``
  Departures (up) and arrivals (down) per hour, stacked by activity type.
- ``trip_duration_by_hour_demand.png`` / ``trip_duration_by_hour_sim.png``
  Trip travel time by departure hour, one panel per destination activity:
  mean, median and the p25-p75 band.
- ``activity_duration_by_type.png``
  Time spent at each activity type, planned against the last iteration.

Where the "demand" side comes from: plans.xml legs carry only a mode — no
departure or travel time — so the hour a later leg departs, and every arrival,
cannot be read from plans.xml alone. ``output/ITERS/it.0/0.plans.xml.gz`` is
plans.xml after MATSim's router, dumped BEFORE the iteration-0 mobsim: every
leg has the router's dep_time and free-flow trav_time, and each departure is
the previous arrival plus max_dur. That is the generated demand with MATSim's
own free-flow travel times, and it is what the demand figures show.

The EXECUTED iteration 0 is not used for timing. It keeps every planned
duration exactly, but on a congested network it is not the plan: on
bham_stage2c_directchains every agent took free-flow shortest paths into
gridlock, a trip to Work at 08:00 averaged 232 min against 60 planned,
arrivals after midnight tripled (62,694 against 20,400 planned), and 34,276
planned activities were never reached. Only when 0.plans.xml.gz is missing is
the executed iteration 0 used, and it is labelled as congested.

The result of the source check goes to ``trip_timing_check.json``, which the
report prints under the figures.

Why these figures exist: evening counts overshoot because discretionary
activities run 2-3x their survey duration under the default scoring. Each
over-long stop pushes every later leg back, so chains start on time and
ratchet late. These figures make that visible in every report.
"""

import gzip
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches

from utils.logger import setup_logger

logger = setup_logger(__name__)

# Fixed activity order and colour. Colour follows the activity, never its rank,
# so a type keeps its colour in all five figures and across runs. Hues are the
# first seven categorical slots of the dataviz reference palette (validated for
# colour-vision deficiency on a white surface; the three light hues rely on the
# legend and the white segment gaps, not on contrast alone).
ACTIVITY_ORDER = ["Home", "Work", "School", "Shopping", "Dining", "Social", "Other"]
ACTIVITY_COLORS = {
    "Home": "#2a78d6",
    "Work": "#eb6834",
    "School": "#1baf7a",
    "Shopping": "#eda100",
    "Dining": "#e87ba4",
    "Social": "#008300",
    "Other": "#4a3aa7",
}
# Types outside ACTIVITY_ORDER are folded into one grey group instead of being
# given a generated hue.
UNLISTED = "Unlisted"
UNLISTED_COLOR = "#8c8c8c"
ALL_COLOR = "#3a434e"
INK = "#1f2328"

DAY_S = 24 * 3600
# Hour bins run 0-23; anything departing or arriving after midnight goes in 23
# and the tick reads "23+". Wrapping to hour 0 would hide the late ratchet.
LAST_HOUR = 23
# Hour x destination cells with fewer trips than this are not drawn in the
# duration figure — a mean over three trips is noise, not a finding.
MIN_TRIPS_PER_CELL = 10
# A duration more than this far from max_dur counts as "not as written".
# MATSim rounds to the second, so a real match is within a few seconds.
DURATION_TOLERANCE_S = 60

FIG_NAMES = {
    "dep_arr_demand": "dep_arr_by_activity_demand.png",
    "dep_arr_sim": "dep_arr_by_activity_sim.png",
    "duration_demand": "trip_duration_by_hour_demand.png",
    "duration_sim": "trip_duration_by_hour_sim.png",
    "activity_duration": "activity_duration_by_type.png",
}
CHECK_NAME = "trip_timing_check.json"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _hms_to_s(values: pd.Series) -> pd.Series:
    """'HH:MM:SS' (hours may exceed 24) to seconds; blanks become NaN."""
    parts = values.astype("string").str.split(":", expand=True)
    if parts.shape[1] < 3:
        return pd.Series(np.nan, index=values.index)
    # float64, not the nullable Float64 the string dtype gives: numpy's nan*
    # functions cannot handle pd.NA.
    parts = parts.iloc[:, :3].apply(pd.to_numeric, errors="coerce").astype("float64")
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _hms_str_to_s(value: Optional[str]) -> Optional[float]:
    if not value or value == "undefined":
        return None
    try:
        h, m, s = value.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except ValueError:
        return None


def _fold_type(types: pd.Series) -> pd.Series:
    return types.where(types.isin(ACTIVITY_ORDER), UNLISTED)


def _ordered_types(present) -> List[str]:
    present = set(present)
    out = [t for t in ACTIVITY_ORDER if t in present]
    if UNLISTED in present:
        out.append(UNLISTED)
    return out


def _color(activity: str) -> str:
    return ACTIVITY_COLORS.get(activity, UNLISTED_COLOR)


def find_iterations(experiment_dir: Path) -> Tuple[Optional[int], Optional[int]]:
    """(0, last) iteration numbers that have both trips and activities files."""
    iters_dir = experiment_dir / "output" / "ITERS"
    found = []
    if iters_dir.is_dir():
        for d in iters_dir.glob("it.*"):
            try:
                n = int(d.name.split(".", 1)[1])
            except (IndexError, ValueError):
                continue
            if (d / f"{n}.trips.csv.gz").is_file() and \
                    (d / f"{n}.activities.csv.gz").is_file():
                found.append(n)
    if not found:
        return None, None
    return (0 if 0 in found else None), max(found)


def load_trips(experiment_dir: Path, iteration: int) -> pd.DataFrame:
    """Trips with departure/arrival hour and travel time in minutes."""
    path = (experiment_dir / "output" / "ITERS" / f"it.{iteration}"
            / f"{iteration}.trips.csv.gz")
    df = pd.read_csv(path, sep=";", usecols=[
        "person", "trip_number", "dep_time", "trav_time",
        "start_activity_type", "end_activity_type"], dtype=str)
    return _trip_frame(df["start_activity_type"], df["end_activity_type"],
                       _hms_to_s(df["dep_time"]), _hms_to_s(df["trav_time"]))


def _trip_frame(from_type, to_type, dep_s, trav_s) -> pd.DataFrame:
    """The trip table both sides share: types, departure, minutes, hour bins."""
    out = pd.DataFrame({
        "from_type": _fold_type(pd.Series(from_type, dtype=object)).values,
        "to_type": _fold_type(pd.Series(to_type, dtype=object)).values,
        "dep_s": np.asarray(dep_s, dtype="float64"),
        "trav_min": np.asarray(trav_s, dtype="float64") / 60.0,
    })
    out = out[out["dep_s"].notna() & out["trav_min"].notna()]
    out["dep_hour"] = (out["dep_s"] // 3600).clip(upper=LAST_HOUR).astype(int)
    arr = out["dep_s"] + out["trav_min"] * 60.0
    out["arr_hour"] = (arr // 3600).clip(upper=LAST_HOUR).astype(int)
    return out


def load_activity_durations(experiment_dir: Path, iteration: int) -> pd.DataFrame:
    """Duration in minutes per activity, with the overnight Home stay joined.

    activities.csv stores the overnight stay as two open-ended rows: the day's
    first activity has a blank start_time, the last a blank end_time. Dropping
    blank-time rows would discard the whole overnight stay and make Home look
    far too short, so the two are joined across midnight here — the same wrap
    MATSim's scoring applies: first end + (24 h - last start).

    Only Home is joined. MATSim also wraps a day that opens and closes at the
    same non-Home type, but in a figure about how long a stop lasts that adds
    a ~19 h "Social" or "Work" stay: on bham_stage2c_directchains 1,442 Social
    wraps lifted the Social mean from 96 to 136 min.
    """
    path = (experiment_dir / "output" / "ITERS" / f"it.{iteration}"
            / f"{iteration}.activities.csv.gz")
    df = pd.read_csv(path, sep=";", usecols=[
        "person", "activity_number", "activity_type", "start_time", "end_time"])
    df = df[~df["activity_type"].astype(str).str.endswith(" interaction")]

    has_start = df["start_time"].notna()
    has_end = df["end_time"].notna()

    closed = df[has_start & has_end]
    parts = [pd.DataFrame({
        "activity_type": closed["activity_type"],
        "dur_min": (closed["end_time"] - closed["start_time"]) / 60.0,
    })]

    first = df[~has_start & has_end].set_index("person")
    last = df[has_start & ~has_end].set_index("person")
    wrap = first[["activity_type", "end_time"]].join(
        last[["activity_type", "start_time"]], how="inner", rsuffix="_last")
    same = ((wrap["activity_type"] == wrap["activity_type_last"])
            & (wrap["activity_type"] == "Home"))
    joined = wrap[same]
    parts.append(pd.DataFrame({
        "activity_type": joined["activity_type"].values,
        "dur_min": ((joined["end_time"] + DAY_S - joined["start_time"])
                    .clip(lower=0) / 60.0).values,
    }))

    # Persons whose day is not a Home-to-Home loop: a plan that starts and ends
    # at different types (72 of 2,129 persons on the Twin Cities fast run,
    # mostly Home...Work), one that opens and closes at the same non-Home type,
    # a chain cut at the end of the simulation, or an agent removed as stuck.
    # Their open rows have no true stop duration, so they are left out rather
    # than guessed.
    n_open = len(first) + len(last)
    n_dropped = n_open - 2 * int(same.sum())
    # A person who never leaves home has one row with both times blank.
    n_stay_home = int((~has_start & ~has_end).sum())
    if n_dropped or n_stay_home:
        logger.info(f"  it.{iteration} activity durations: left out {n_dropped} "
                    f"open-ended rows that are not a Home-to-Home overnight "
                    f"stay, and {n_stay_home} all-day stays")

    out = pd.concat(parts, ignore_index=True)
    out["activity_type"] = _fold_type(out["activity_type"])
    return out[out["dur_min"].notna()]


def load_typical_durations(experiment_dir: Path) -> Dict[str, float]:
    """typicalDuration (minutes) per activity type from the run's config.xml."""
    path = experiment_dir / "config.xml"
    if not path.is_file():
        return {}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return {}
    out: Dict[str, float] = {}
    for module in root.iter("module"):
        if module.get("name") not in ("scoring", "planCalcScore"):
            continue
        for ps in module.iter("parameterset"):
            if ps.get("type") != "activityParams":
                continue
            params = {p.get("name"): p.get("value") for p in ps.findall("param")}
            seconds = _hms_str_to_s(params.get("typicalDuration"))
            if params.get("activityType") and seconds is not None:
                out[params["activityType"]] = seconds / 60.0
    return out


# ---------------------------------------------------------------------------
# Planned schedule: plans.xml as routed by MATSim before the it.0 mobsim
# ---------------------------------------------------------------------------

def planned_plans_path(experiment_dir: Path) -> Optional[Path]:
    """The routed iteration-0 plans, dumped before the mobsim, if written."""
    path = experiment_dir / "output" / "ITERS" / "it.0" / "0.plans.xml.gz"
    return path if path.is_file() else None


def load_planned(plans_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """Planned trips and activity durations from the routed iteration-0 plans.

    Each leg carries the router's dep_time and trav_time: free-flow for car,
    timetable for pt, teleported for walk. A trip runs from one main activity
    to the next; the "... interaction" stage activities between its legs are
    skipped, and its travel time is the last leg's arrival minus the first
    leg's departure. An activity lasts from the arrival of the trip into it to
    the departure of the trip out of it; the overnight Home stay is joined
    across midnight, as on the simulation side.

    Returns (trips, durations, stats). stats counts how many activities keep
    their max_dur in the router's schedule — a check that this file really is
    the plan, not an executed day.
    """
    from_t, to_t, deps, travs = [], [], [], []
    dur_type, dur_min = [], []
    n_persons = n_acts = n_sched = n_off = n_no_time = 0
    max_off = 0.0
    with gzip.open(plans_path, "rb") as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != "person":
                continue
            plan = next((p for p in el.findall("plan")
                         if p.get("selected", "yes") == "yes"), None)
            # One entry per main activity: [type, arrival_s, departure_s, max_dur_s]
            acts: List[list] = []
            trip_dep = trip_end = None
            if plan is not None:
                n_persons += 1
                for e in plan:
                    if e.tag == "leg":
                        dep = _hms_str_to_s(e.get("dep_time"))
                        tt = _hms_str_to_s(e.get("trav_time"))
                        if tt is None:
                            route = e.find("route")
                            if route is not None:
                                tt = _hms_str_to_s(route.get("trav_time"))
                        if dep is None:
                            dep = trip_end  # a later leg of the same trip
                        if dep is None or tt is None:
                            n_no_time += 1
                            dep = dep if dep is not None else 0.0
                            tt = tt if tt is not None else 0.0
                        if trip_dep is None:
                            trip_dep = dep
                            if acts:
                                acts[-1][2] = dep
                        trip_end = dep + tt
                    elif e.tag == "activity":
                        a_type = e.get("type")
                        if a_type.endswith(" interaction"):
                            continue
                        arrival = None
                        if trip_dep is not None and acts:
                            from_t.append(acts[-1][0])
                            to_t.append(a_type)
                            deps.append(trip_dep)
                            travs.append(trip_end - trip_dep)
                            arrival = trip_end
                        acts.append([a_type, arrival, None,
                                     _hms_str_to_s(e.get("max_dur"))])
                        trip_dep = trip_end = None
            el.clear()

            n_acts += len(acts)
            for a_type, arr, dep, max_dur in acts:
                if arr is None or dep is None:
                    continue
                dur_type.append(a_type)
                dur_min.append((dep - arr) / 60.0)
                if max_dur is not None:
                    n_sched += 1
                    off = abs(dep - arr - max_dur)
                    max_off = max(max_off, off)
                    if off > DURATION_TOLERANCE_S:
                        n_off += 1
            if (len(acts) >= 2 and acts[0][0] == "Home" and acts[-1][0] == "Home"
                    and acts[0][2] is not None and acts[-1][1] is not None):
                dur_type.append("Home")
                dur_min.append(max(acts[0][2] + DAY_S - acts[-1][1], 0.0) / 60.0)

    trips = _trip_frame(from_t, to_t, deps, travs)
    durations = pd.DataFrame({
        "activity_type": _fold_type(pd.Series(dur_type, dtype=object)).values,
        "dur_min": dur_min,
    })
    stats = {
        "source": "it0_plans",
        "persons": n_persons,
        "planned_trips": len(deps),
        "planned_activities": n_acts,
        "legs_without_time": n_no_time,
        "schedule_checked": n_sched,
        "schedule_off": n_off,
        "schedule_max_diff_s": max_off,
        "tolerance_s": DURATION_TOLERANCE_S,
    }
    return trips, durations, stats


def _count_executed_activities(experiment_dir: Path) -> Optional[int]:
    """Main activities the executed iteration 0 actually reached."""
    path = experiment_dir / "output" / "ITERS" / "it.0" / "0.activities.csv.gz"
    if not path.is_file():
        return None
    types = pd.read_csv(path, sep=";", usecols=["activity_type"])["activity_type"]
    return int((~types.astype(str).str.endswith(" interaction")).sum())


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _hour_axis(ax):
    ax.set_xticks(range(0, 24))
    ax.set_xticklabels([str(h) for h in range(LAST_HOUR)] + [f"{LAST_HOUR}+"],
                       fontsize=8)
    ax.set_xlim(-0.6, LAST_HOUR + 0.6)


def _hourly_counts(trips: pd.DataFrame, hour_col: str, type_col: str) -> pd.DataFrame:
    return (trips.groupby([hour_col, type_col]).size().unstack(fill_value=0)
            .reindex(range(24), fill_value=0))


def plot_dep_arr(trips: pd.DataFrame, types: List[str], ylim: float,
                 title: str, path: Path) -> None:
    """Departures stacked up from zero, arrivals stacked down, by activity."""
    dep = _hourly_counts(trips, "dep_hour", "from_type")
    arr = _hourly_counts(trips, "arr_hour", "to_type")
    hours = np.arange(24)

    fig, ax = plt.subplots(figsize=(13, 6))
    up = np.zeros(24)
    down = np.zeros(24)
    for t in types:
        d = dep[t].values if t in dep else np.zeros(24)
        a = arr[t].values if t in arr else np.zeros(24)
        # White edges give the 2px-style gap between stacked segments, so
        # adjacent types stay distinct without relying on colour alone.
        ax.bar(hours, d, bottom=up, width=0.8, color=_color(t),
               edgecolor="white", linewidth=0.6, label=t)
        ax.bar(hours, -a, bottom=-down, width=0.8, color=_color(t),
               edgecolor="white", linewidth=0.6)
        up += d
        down += a

    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_ylim(-ylim, ylim)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"{abs(v):,.0f}"))
    ax.set_ylabel("Trips per hour (sample, not scaled)")
    ax.set_xlabel("Hour of Day")
    _hour_axis(ax)
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    ax.text(0.01, 0.97, "Departures, by activity left", transform=ax.transAxes,
            va="top", fontsize=9, color="#5a6470")
    ax.text(0.01, 0.03, "Arrivals, by activity reached", transform=ax.transAxes,
            va="bottom", fontsize=9, color="#5a6470")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9,
              frameon=False, title="Activity", title_fontsize=9)
    ax.set_title(title, fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved {path.name}")


def _duration_stats(trips: pd.DataFrame) -> pd.DataFrame:
    g = trips.groupby("dep_hour")["trav_min"]
    stats = pd.DataFrame({
        "n": g.size(), "mean": g.mean(), "median": g.median(),
        "p25": g.quantile(0.25), "p75": g.quantile(0.75),
    }).reindex(range(24))
    stats.loc[~(stats["n"] >= MIN_TRIPS_PER_CELL),
              ["mean", "median", "p25", "p75"]] = np.nan
    return stats


def _duration_panels(trips: pd.DataFrame, types: List[str]):
    panels = [("All trips", ALL_COLOR, _duration_stats(trips), len(trips))]
    for t in types:
        sub = trips[trips["to_type"] == t]
        panels.append((f"To {t}", _color(t), _duration_stats(sub), len(sub)))
    return panels


def _duration_ymax(panels) -> float:
    """Axis top from hours 0-22 only.

    The 23+ bin collects every trip after midnight, and it can hold trips that
    last many hours: on bham_stage2c_directchains the planned walk trips
    departing in 23+ averaged 435 min (router fallback from pt when no service
    runs), which set a 0-680 min axis and flattened every other hour on both
    sides of the pair. Values above the axis are printed instead of drawn.
    """
    peaks = [np.nanmax(s.loc[:LAST_HOUR - 1, ["mean", "p75"]].values)
             for _, _, s, _ in panels
             if s.loc[:LAST_HOUR - 1, "mean"].notna().any()]
    return max(peaks) if peaks else 60.0


def plot_duration(panels, ymax: float, title: str, path: Path) -> None:
    """Small multiples: one panel per destination, shared axes."""
    ncols = 4
    nrows = math.ceil(len(panels) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(15, 3.6 * nrows + 0.8),
                             sharex=True, sharey=True, squeeze=False)
    hours = np.arange(24)
    for ax, (label, color, s, n) in zip(axes.flat, panels):
        ax.fill_between(hours, s["p25"], s["p75"], color=color, alpha=0.22,
                        linewidth=0)
        # Markers, because an hour with enough trips between two that have too
        # few is a single point, and a line through one point draws nothing.
        ax.plot(hours, s["mean"], color=color, linewidth=2, marker="o",
                markersize=3)
        ax.plot(hours, s["median"], color=color, linewidth=1.4,
                linestyle=(0, (4, 2)), marker="o", markersize=2.5,
                markerfacecolor="white")
        ax.set_title(f"{label}  (n={n:,})", fontsize=10, loc="left")
        if not s["mean"].notna().any():
            ax.text(0.5, 0.5, f"fewer than {MIN_TRIPS_PER_CELL} trips\nin every hour",
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=9, color="#5a6470")
        ax.grid(True, alpha=0.3)
        ax.set_xticks(range(0, 24, 3))
        ax.tick_params(axis="x", labelsize=8)
        ax.set_xlim(-0.5, LAST_HOUR + 0.5)
    top = ymax * 1.05
    for ax, (_, color, s, _) in zip(axes.flat, panels):
        # A mean above the axis is clipped, so print its value at the top edge.
        for h, v in s["mean"].items():
            if pd.notna(v) and v > top:
                ax.annotate(f"mean {v:.0f}", xy=(h, top), xytext=(-3, -3),
                            textcoords="offset points", ha="right", va="top",
                            fontsize=8, color=INK)
                ax.plot([h], [top], marker="^", color=color, markersize=6,
                        clip_on=False)
    for ax in axes.flat[len(panels):]:
        ax.set_visible(False)
    axes[0, 0].set_ylim(0, top)
    for ax in axes[:, 0]:
        ax.set_ylabel("Trip duration [min]")
    for ax in axes[-1, :]:
        ax.set_xlabel("Departure hour (23 = 23+)")

    handles = [
        Line2D([], [], color=ALL_COLOR, linewidth=2, marker="o", markersize=3,
               label="mean"),
        Line2D([], [], color=ALL_COLOR, linewidth=1.4, linestyle=(0, (4, 2)),
               marker="o", markersize=2.5, markerfacecolor="white",
               label="median"),
        mpatches.Patch(color=ALL_COLOR, alpha=0.22, label="p25 to p75"),
    ]
    fig.legend(handles=handles, loc="upper right", ncol=3, fontsize=9,
               frameon=False, bbox_to_anchor=(0.99, 1.0))
    fig.suptitle(title, fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.text(0.01, 0.005, f"Hours with fewer than {MIN_TRIPS_PER_CELL} trips "
             f"are not drawn. The axis is set from hours 0-22; a mean above it "
             f"is marked with its value.", fontsize=8, color="#5a6470")
    plt.tight_layout(rect=(0, 0.02, 1, 0.96))
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved {path.name}")


def plot_activity_durations(dur0: pd.DataFrame, durN: pd.DataFrame,
                            last_it: int, typical: Dict[str, float],
                            title: str, path: Path,
                            label0: str = "planned (free-flow schedule)") -> None:
    """Boxes per type: planned hollow, last iteration filled, log minutes."""
    types = _ordered_types(set(dur0["activity_type"]) | set(durN["activity_type"]))
    fig, ax = plt.subplots(figsize=(13, 6))
    box_kw = dict(widths=0.34, whis=(5, 95), showfliers=False,
                  patch_artist=True, manage_ticks=False)

    for i, t in enumerate(types):
        color = _color(t)
        v0 = dur0.loc[dur0["activity_type"] == t, "dur_min"].clip(lower=0.5)
        vN = durN.loc[durN["activity_type"] == t, "dur_min"].clip(lower=0.5)
        for vals, x, filled in ((v0, i - 0.2, False), (vN, i + 0.2, True)):
            if len(vals) == 0:
                continue
            bp = ax.boxplot([vals.values], positions=[x], **box_kw)
            for box in bp["boxes"]:
                box.set_facecolor(color if filled else "white")
                box.set_edgecolor(color)
                box.set_linewidth(1.4)
            for part in ("whiskers", "caps"):
                for line in bp[part]:
                    line.set_color(color)
                    line.set_linewidth(1.2)
            for line in bp["medians"]:
                line.set_color(INK if filled else color)
                line.set_linewidth(1.6)
        if t in typical:
            ax.hlines(typical[t], i - 0.44, i + 0.44, colors=INK,
                      linestyles=(0, (4, 2)), linewidth=1.3)
        if len(v0) and len(vN) and v0.median() > 0:
            ratio = vN.median() / v0.median()
            ax.text(i, 0.97, f"x{ratio:.2f}", transform=ax.get_xaxis_transform(),
                    ha="center", va="top", fontsize=10, fontweight="bold",
                    color=INK)

    ax.set_yscale("log")
    ticks = [1, 2, 5, 10, 15, 30, 60, 120, 240, 480, 960, 1440]
    ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"{v:g} min" if v < 60 else f"{v / 60:g} h"))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    # Lowest p5 whisker of any box, so no whisker runs off the axis.
    lo = min(d.groupby("activity_type")["dur_min"].quantile(0.05).min()
             for d in (dur0, durN) if len(d))
    ax.set_ylim(max(lo * 0.8, 1), 1440 * 1.9)
    ax.set_xticks(range(len(types)))
    ax.set_xticklabels(types)
    ax.set_xlim(-0.6, len(types) - 0.4)
    ax.set_ylabel("Time at activity (log scale)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    handles = [
        mpatches.Patch(facecolor="white", edgecolor=ALL_COLOR, linewidth=1.4,
                       label=label0),
        mpatches.Patch(facecolor=ALL_COLOR, edgecolor=ALL_COLOR,
                       label=f"iteration {last_it} (simulated)"),
        Line2D([], [], color=INK, linestyle=(0, (4, 2)), linewidth=1.3,
               label="config typicalDuration"),
    ]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0),
              fontsize=9, frameon=False)
    ax.text(1.01, 0.62, "Box: p25 to p75\nWhiskers: p5 to p95\n"
            "xN: median ratio,\nsimulated / planned", transform=ax.transAxes,
            fontsize=8, color="#5a6470", va="top")
    ax.set_title(title, fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved {path.name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def plot_trip_timing(experiment_dir: Path, evaluation_dir: Path) -> Optional[Dict]:
    """Write the five figures and trip_timing_check.json. Returns the check."""
    experiment_dir = Path(experiment_dir)
    evaluation_dir = Path(evaluation_dir)
    first_it, last_it = find_iterations(experiment_dir)
    if last_it is None:
        logger.warning("Trip timing figures skipped: no output/ITERS/it.N with "
                       "trips and activities files")
        return None
    name = experiment_dir.name

    plans0 = planned_plans_path(experiment_dir)
    if plans0 is not None:
        logger.info(f"Trip timing figures: planned schedule "
                    f"({plans0.relative_to(experiment_dir)}) against iteration "
                    f"{last_it}")
        trips0, dur0, check = load_planned(plans0)
        demand_label = "Planned demand (free-flow schedule)"
        label0 = "planned (free-flow schedule)"
        # How much of the plan the executed iteration 0 reached. Not used in
        # any figure; printed in the report so a gridlocked it.0 is visible.
        executed = _count_executed_activities(experiment_dir)
        if executed is not None:
            check["it0_activities_executed"] = executed
        if check["schedule_off"] or check["legs_without_time"]:
            logger.warning(
                f"0.plans.xml.gz does not follow plans.xml exactly: "
                f"{check['schedule_off']} of {check['schedule_checked']} "
                f"activities differ from max_dur by more than "
                f"{DURATION_TOLERANCE_S} s, {check['legs_without_time']} legs "
                f"have no router time.")
    elif first_it == 0:
        logger.warning("Trip timing: output/ITERS/it.0/0.plans.xml.gz not found. "
                       "The demand side falls back to the EXECUTED iteration 0, "
                       "which includes iteration-0 congestion and is not the plan.")
        trips0 = load_trips(experiment_dir, 0)
        dur0 = load_activity_durations(experiment_dir, 0)
        check = {"source": "it0_executed"}
        demand_label = "Iteration 0 executed (congested, not the plan)"
        label0 = "iteration 0 executed (congested)"
    else:
        logger.warning("Trip timing figures skipped: neither 0.plans.xml.gz nor "
                       "iteration 0 output found")
        return None
    check["last_iteration"] = last_it
    (evaluation_dir / CHECK_NAME).write_text(json.dumps(check, indent=2),
                                             encoding="utf-8")

    tripsN = load_trips(experiment_dir, last_it)
    types = _ordered_types(set(trips0["from_type"]) | set(trips0["to_type"])
                           | set(tripsN["from_type"]) | set(tripsN["to_type"]))
    sim_label = f"Simulation (iteration {last_it})"

    # Same y-limit on both sides of each pair, so bar heights compare directly.
    peak = 0
    for t in (trips0, tripsN):
        peak = max(peak, t.groupby("dep_hour").size().max(),
                   t.groupby("arr_hour").size().max())
    ylim = peak * 1.08
    plot_dep_arr(trips0, types, ylim,
                 f"Departures and arrivals per hour — {demand_label} — {name}",
                 evaluation_dir / FIG_NAMES["dep_arr_demand"])
    plot_dep_arr(tripsN, types, ylim,
                 f"Departures and arrivals per hour — {sim_label} — {name}",
                 evaluation_dir / FIG_NAMES["dep_arr_sim"])

    panels0 = _duration_panels(trips0, types)
    panelsN = _duration_panels(tripsN, types)
    ymax = max(_duration_ymax(panels0), _duration_ymax(panelsN))
    plot_duration(panels0, ymax,
                  f"Trip duration by departure hour — {demand_label} — {name}",
                  evaluation_dir / FIG_NAMES["duration_demand"])
    plot_duration(panelsN, ymax,
                  f"Trip duration by departure hour — {sim_label} — {name}",
                  evaluation_dir / FIG_NAMES["duration_sim"])

    durN = load_activity_durations(experiment_dir, last_it)
    plot_activity_durations(
        dur0, durN, last_it, load_typical_durations(experiment_dir),
        f"Time at activity — planned against iteration {last_it} — {name}",
        evaluation_dir / FIG_NAMES["activity_duration"], label0=label0)
    return check
