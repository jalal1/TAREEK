# SPDX-License-Identifier: GPL-3.0-or-later
"""The scenario file: what to change in a baseline run.

The format is the contract with TAREEK-Vis, which writes these files. See
scenarios/README.md ("The scenario file"). Keys that start with '_' are
comments, as in the TAREEK config files.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

CLOSURE_TYPES = ('close',)
NAME_PATTERN = re.compile(r'^[A-Za-z0-9_-]+$')


class ScenarioError(ValueError):
    """The scenario file or its base run cannot be used. The message says why."""


@dataclass
class Closure:
    type: str
    link_ids: List[str]


@dataclass
class Scenario:
    name: str
    base_experiment: str
    closures: List[Closure]
    description: str = ''
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def closed_link_ids(self) -> List[str]:
        """Every link a closure names, in file order, each once."""
        seen = {}
        for closure in self.closures:
            if closure.type == 'close':
                for link_id in closure.link_ids:
                    seen.setdefault(link_id, None)
        return list(seen)


def _strip_comments(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if not k.startswith('_')}
    if isinstance(obj, list):
        return [_strip_comments(v) for v in obj]
    return obj


def parse_scenario(data: Dict[str, Any]) -> Scenario:
    """Check a scenario dict and return it as a Scenario."""
    if not isinstance(data, dict):
        raise ScenarioError("The scenario file must hold one JSON object.")
    raw = data
    data = _strip_comments(data)

    name = data.get('name')
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        raise ScenarioError(
            f"'name' must be letters, digits, '_' or '-' only (got {name!r}). "
            "It becomes part of the output folder name.")

    base = data.get('base_experiment')
    if not isinstance(base, str) or not base.strip():
        raise ScenarioError("'base_experiment' is required: the folder name of the baseline run.")

    description = data.get('description', '')
    if not isinstance(description, str):
        raise ScenarioError("'description' must be text.")

    entries = data.get('closures')
    if not isinstance(entries, list) or not entries:
        raise ScenarioError("'closures' must be a list with at least one entry.")

    closures = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ScenarioError(f"closures[{i}] must be an object.")
        ctype = entry.get('type')
        if ctype not in CLOSURE_TYPES:
            raise ScenarioError(
                f"closures[{i}].type is {ctype!r}; supported types: {', '.join(CLOSURE_TYPES)}.")
        link_ids = entry.get('link_ids')
        if not isinstance(link_ids, list) or not link_ids:
            raise ScenarioError(f"closures[{i}].link_ids must be a non-empty list.")
        # IDs are strings in network.xml. A tool that wrote numbers still
        # means the same links, so accept integers but not anything else.
        cleaned = []
        for link_id in link_ids:
            if isinstance(link_id, bool) or not isinstance(link_id, (str, int)):
                raise ScenarioError(f"closures[{i}].link_ids has a bad entry: {link_id!r}.")
            text = str(link_id).strip()
            if not text:
                raise ScenarioError(f"closures[{i}].link_ids has an empty entry.")
            cleaned.append(text)
        closures.append(Closure(type=ctype, link_ids=cleaned))

    return Scenario(name=name, base_experiment=base.strip(), closures=closures,
                    description=description, raw=raw)


def load_scenario(path: Path) -> Scenario:
    path = Path(path)
    if not path.is_file():
        raise ScenarioError(f"Scenario file not found: {path}")
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ScenarioError(f"Scenario file is not valid JSON: {path}: {e}")
    return parse_scenario(data)
