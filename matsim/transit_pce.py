"""Scale transit vehicle PCE to the simulation sample size.

pt2matsim writes transitVehicles.xml with full-size passenger car
equivalents (Bus 2.8, Rail 27.1, ...). The car demand is a sample, and link
capacity is scaled by ``flowCapacityFactor``, but transit runs the full real
schedule. Hermes applies PCE (``ScenarioImporter`` builds
``flowCapacityPCEs`` / ``storageCapacityPCEs`` from the vehicle types), so on
a 10% network one unscaled bus takes the road space of ~28 sampled cars.

The usual MATSim practice is to scale each transit vehicle type's PCE by the
sample size (pce x flowCapacityFactor). Buses then take their real share of
road space and are still delayed by congestion. Thinning the schedule instead
would cut frequency and make pt waits N times longer.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

MARKER_NAME = 'transit_pce_scaling.json'

# Optional namespace prefix: pt2matsim writes plain tags, but a file that
# network_generator patched with ElementTree comes back as <ns0:vehicleType>.
_VTYPE_RE = re.compile(
    r'(<(?:\w+:)?vehicleType\b[^>]*\bid="([^"]+)"[^>]*>)(.*?)(</(?:\w+:)?vehicleType>)', re.S)
_PCE_RE = re.compile(r'(<(?:\w+:)?passengerCarEquivalents\b[^>]*\bpce=")([^"]+)(")')


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def scale_transit_pce(vehicles_path: Path, factor: float,
                      marker_path: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """Scale every vehicle type's PCE in ``vehicles_path`` by ``factor``, in place.

    Idempotent: a marker file next to the vehicles file records the original
    and the written PCE per type. On a rerun, a type whose current PCE equals
    the recorded written value is treated as already scaled, and the new value
    is computed from the recorded original. So a second call with the same
    factor changes nothing, and a call with another factor rescales from the
    original instead of compounding. A type whose PCE matches neither (for
    example a freshly copied file) is taken as the original.

    Returns ``{type_id: {'original': x, 'scaled': y}}``.
    """
    vehicles_path = Path(vehicles_path)
    marker_path = Path(marker_path) if marker_path else vehicles_path.parent / MARKER_NAME

    previous = {}
    if marker_path.exists():
        try:
            previous = json.loads(marker_path.read_text()).get('types', {})
        except (OSError, ValueError):
            logger.warning(f"Unreadable {marker_path.name}, treating current PCE as original")

    with open(vehicles_path, encoding='utf-8', newline='') as f:
        text = f.read()
    result: Dict[str, Dict[str, float]] = {}

    def _scale_type(m: re.Match) -> str:
        type_id, body = m.group(2), m.group(3)
        pce_m = _PCE_RE.search(body)
        if pce_m is None:
            logger.warning(f"  Transit vehicle type {type_id} has no passengerCarEquivalents "
                           f"(MATSim default 1.0); not scaled")
            return m.group(0)
        current = float(pce_m.group(2))
        prev = previous.get(type_id)
        if prev is not None and abs(current - prev['scaled']) < 1e-9:
            original = prev['original']
        else:
            original = current
        scaled = float(_fmt(original * factor))
        result[type_id] = {'original': original, 'scaled': scaled}
        new_body = body[:pce_m.start(2)] + _fmt(scaled) + body[pce_m.end(2):]
        return m.group(1) + new_body + m.group(4)

    new_text = _VTYPE_RE.sub(_scale_type, text)

    if not result:
        logger.warning(f"  No vehicle type with a PCE found in {vehicles_path.name}; nothing scaled")
    if new_text != text:
        with open(vehicles_path, 'w', encoding='utf-8', newline='') as f:
            f.write(new_text)
    marker_path.write_text(json.dumps({'flowCapacityFactor': factor, 'types': result}, indent=2))

    for type_id, v in result.items():
        logger.info(f"  {type_id}: pce {_fmt(v['original'])} -> {_fmt(v['scaled'])}")
    if result and new_text == text:
        logger.info("  Transit PCE already equals original x factor; file unchanged")
    return result
