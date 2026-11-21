# SPDX-License-Identifier: GPL-3.0-or-later
"""Give roundabout links a realistic capacity.

pt2matsim picks a link's default settings from its ``highway`` tag only
(``OsmMultimodalNetworkConverter.getWayDefaultParams``). It reads
``junction=roundabout`` only to make the link one-way. So a roundabout on a
tertiary road gets the tertiary lane capacity (600 veh/h), and every movement
through the ring shares that 600 veh/h. A real single-lane roundabout carries
about 1,100-1,400 veh/h (HCM). In Sartell (Stearns County MN) the roundabouts
on Pine Cone Road became the queue heads of the morning peak.

pt2matsim reads no capacity tag, and a ``junction`` way default is never used,
so the fix is a step after the network is built: each link with
``osm:way:junction=roundabout`` gets ``capacity = per_lane x permlanes``. The
capacity is only raised, never lowered, so the step is idempotent and leaves
roundabouts that already have more capacity (a multi-lane highway roundabout)
unchanged. Link IDs, lanes, speeds and geometry do not change.

Config: ``network.roundabout_capacity_per_lane`` (veh/h per lane). Missing or
null means off, so regions that do not set it keep the old network.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

MARKER_NAME = 'roundabout_capacity.json'

_CAP_RE = re.compile(r'(\bcapacity=")([^"]+)(")')
_LANES_RE = re.compile(r'\bpermlanes="([^"]+)"')
_ID_RE = re.compile(r'\bid="([^"]+)"')
_ROUNDABOUT_RE = re.compile(r'name="osm:way:junction"[^>]*>\s*roundabout\s*<')


def apply_roundabout_capacity(network_path: Path, per_lane: float,
                              marker_path: Optional[Path] = None) -> Dict:
    """Raise the capacity of roundabout links in ``network_path``, in place.

    Streams the file line by line, so it works on large regional networks.
    Writes a marker file next to the network with the count and the changed
    link IDs. Returns the same summary.
    """
    network_path = Path(network_path)
    marker_path = Path(marker_path) if marker_path else network_path.parent / MARKER_NAME
    per_lane = float(per_lane)
    tmp_path = network_path.with_name(network_path.name + '.tmp')

    n_roundabout = 0
    changed: Dict[str, Dict[str, float]] = {}

    def _flush(block):
        nonlocal n_roundabout
        text = ''.join(block)
        if not _ROUNDABOUT_RE.search(text):
            return text
        n_roundabout += 1
        head = block[0]
        cap_m, lanes_m = _CAP_RE.search(head), _LANES_RE.search(head)
        if cap_m is None:
            return text
        lanes = float(lanes_m.group(1)) if lanes_m else 1.0
        current = float(cap_m.group(2))
        target = per_lane * max(lanes, 1.0)
        if target <= current:
            return text
        link_id = _ID_RE.search(head).group(1)
        changed[link_id] = {'from': current, 'to': target}
        block[0] = head[:cap_m.start(2)] + f"{target:.1f}" + head[cap_m.end(2):]
        return ''.join(block)

    with open(network_path, encoding='utf-8', newline='') as src, \
            open(tmp_path, 'w', encoding='utf-8', newline='') as dst:
        block = None
        for line in src:
            if block is None:
                if '<link ' in line and '/>' not in line and '</link>' not in line:
                    block = [line]
                else:
                    dst.write(line)
            else:
                block.append(line)
                if '</link>' in line:
                    dst.write(_flush(block))
                    block = None
        if block is not None:
            dst.write(''.join(block))

    if changed:
        os.replace(tmp_path, network_path)
    else:
        tmp_path.unlink()

    summary = {
        'roundabout_capacity_per_lane': per_lane,
        'roundabout_links': n_roundabout,
        'links_raised': len(changed),
        'links': changed,
    }
    marker_path.write_text(json.dumps(summary, indent=2))
    logger.info(f"Roundabout capacity: {n_roundabout} roundabout link(s), "
                f"{len(changed)} raised to {per_lane:.0f} veh/h per lane")
    if n_roundabout == 0:
        logger.warning("  No link has osm:way:junction=roundabout; the network may lack OSM tags")
    return summary
