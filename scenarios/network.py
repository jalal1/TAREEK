# SPDX-License-Identifier: GPL-3.0-or-later
"""Read a MATSim network.xml and close links in a copy of it.

A closed link stays in the file with its ID; only 'car' is removed from its
modes. Keeping the link keeps the IDs of the baseline and the scenario run the
same, so the two can be compared link by link, and the transit schedule (bus
lines are fixed lists of links) stays valid. Trucks use mode 'car', so they
are closed out too.
"""

import gzip
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import networkx as nx

from utils.logger import setup_logger

logger = setup_logger(__name__)

CAR = 'car'
# Mode written on a link that has no mode left after 'car' is removed. No
# agent uses it, so nothing routes on the link, but the link keeps a non-empty
# modes attribute.
CLOSED_MODE = 'closed'

_LINK_ID = re.compile(r'<link\s[^>]*?\bid="([^"]*)"')
_MODES = re.compile(r'(\bmodes=")([^"]*)(")')


@dataclass
class LinkInfo:
    from_node: str
    to_node: str
    modes: frozenset
    length: float = 0.0
    freespeed: float = 0.0
    capacity: float = 0.0
    lanes: float = 0.0
    highway: str = ''
    name: str = ''
    junction: str = ''


def _open_text(path: Path, mode: str):
    path = Path(path)
    if path.suffix == '.gz':
        return gzip.open(path, mode + 't', encoding='utf-8')
    return open(path, mode, encoding='utf-8')


def _float(value: Optional[str]) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_network(path: Path) -> Tuple[Dict[str, LinkInfo], Dict[str, Tuple[float, float]]]:
    """Return ({link_id: LinkInfo}, {node_id: (x, y)}) for a network.xml(.gz)."""
    links: Dict[str, LinkInfo] = {}
    nodes: Dict[str, Tuple[float, float]] = {}
    with _open_text(path, 'r') as f:
        for _, elem in ET.iterparse(f, events=('end',)):
            tag = elem.tag
            if tag == 'node':
                nodes[elem.get('id')] = (_float(elem.get('x')), _float(elem.get('y')))
                elem.clear()
            elif tag == 'link':
                attrs = {a.get('name'): (a.text or '') for a in elem.iter('attribute')}
                modes = frozenset(m.strip() for m in (elem.get('modes') or '').split(',') if m.strip())
                links[elem.get('id')] = LinkInfo(
                    from_node=elem.get('from'),
                    to_node=elem.get('to'),
                    modes=modes,
                    length=_float(elem.get('length')),
                    freespeed=_float(elem.get('freespeed')),
                    capacity=_float(elem.get('capacity')),
                    lanes=_float(elem.get('permlanes')),
                    highway=attrs.get('osm:way:highway', '') or attrs.get('type', ''),
                    name=attrs.get('osm:way:name', ''),
                    junction=attrs.get('osm:way:junction', ''),
                )
                elem.clear()
    if not links:
        raise ValueError(f"No links found in {path}")
    return links, nodes


def modes_after_closure(modes: Iterable[str]) -> List[str]:
    """The modes a closed link keeps: everything but car, or the placeholder."""
    kept = sorted(m for m in modes if m != CAR)
    return kept or [CLOSED_MODE]


def _main_car_links(links: Dict[str, LinkInfo], excluded: Set[str]) -> Set[str]:
    """Car links inside the largest strongly connected piece of the car network.

    A link outside it can be driven into but not out of, or the other way;
    MATSim cannot route a trip that starts or ends there.
    """
    graph = nx.DiGraph()
    for link_id, info in links.items():
        if link_id not in excluded and CAR in info.modes:
            graph.add_edge(info.from_node, info.to_node)
    if graph.number_of_nodes() == 0:
        return set()
    main = max(nx.strongly_connected_components(graph), key=len)
    return {
        link_id for link_id, info in links.items()
        if link_id not in excluded and CAR in info.modes
        and info.from_node in main and info.to_node in main
    }


def find_cut_off_links(links: Dict[str, LinkInfo], closed: Iterable[str]) -> List[str]:
    """Car links that the closure cuts off from the main car network.

    Example: closing a freeway between two exits leaves the stretch from the
    last on-ramp to the closure open to enter but with no way out. Only links
    that were in the main car network before the closure are returned; a piece
    that was already cut off in the baseline is left as it was.
    """
    closed = set(closed)
    before = _main_car_links(links, set())
    after = _main_car_links(links, closed)
    return sorted(before - after - closed, key=_sort_key)


def _sort_key(link_id: str):
    return (0, int(link_id), '') if link_id.isdigit() else (1, 0, link_id)


def write_closed_network(src: Path, dst: Path, closed: Iterable[str]) -> int:
    """Copy src to dst with 'car' removed from each closed link.

    Streams the file line by line and changes only the modes attribute of the
    closed links, so the rest of the file is byte-for-byte the same. Returns
    the number of links changed; raises if any closed link was not found on a
    single <link ...> line.
    """
    closed = set(closed)
    changed = set()
    with _open_text(src, 'r') as fin, _open_text(dst, 'w') as fout:
        for line in fin:
            if '<link' in line:
                match = _LINK_ID.search(line)
                if match:
                    link_id = html.unescape(match.group(1))
                    if link_id in closed:
                        modes_match = _MODES.search(line)
                        if not modes_match:
                            raise ValueError(f"Link {link_id} has no modes attribute in {src}")
                        old = [m.strip() for m in modes_match.group(2).split(',') if m.strip()]
                        new = ','.join(modes_after_closure(old))
                        line = _MODES.sub(lambda m: m.group(1) + new + m.group(3), line, count=1)
                        changed.add(link_id)
            fout.write(line)
    missing = closed - changed
    if missing:
        raise ValueError(
            f"{len(missing)} closed link(s) were not found as one-line <link> "
            f"elements in {src}: {sorted(missing, key=_sort_key)[:10]}")
    return len(changed)
