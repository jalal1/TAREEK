# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a scenario: the baseline's MATSim run again, with links closed.

Nothing is generated again. The baseline config.xml is copied unchanged, with
every input file it names, so the scenario has the same people, trips,
settings, random seed, iterations and sample. Only network.xml is edited.
See scenarios/README.md ("What a scenario run does").
"""

import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from scenarios.definition import Scenario, ScenarioError, load_scenario
from scenarios.network import (CAR, find_cut_off_links, modes_after_closure,
                               read_network, write_closed_network, CLOSED_MODE)
from utils.logger import reconfigure_logger_to_experiment_dir, setup_logger

logger = setup_logger(__name__)

SUMMARY_FILE = 'scenario_summary.json'
SCENARIO_COPY = 'scenario.json'
# Files a normal run writes next to config.xml that the evaluation and the
# compare report read. They are not named in config.xml.
EXTRA_FILES = ('config_used.json', 'matched_devices.csv')


def _config_param(config_path: Path, module: str, name: str) -> Optional[str]:
    root = ET.parse(config_path).getroot()
    for mod in root.findall('module'):
        if mod.get('name') == module:
            for param in mod.findall('param'):
                if param.get('name') == name:
                    return param.get('value')
    return None


def network_file_name(config_path: Path) -> str:
    """The network file that config.xml names, relative to its folder."""
    return _config_param(config_path, 'network', 'inputNetworkFile') or 'network.xml'


def _input_files(config_path: Path) -> List[str]:
    """Relative file names in config.xml that exist next to it."""
    base_dir = config_path.parent
    names = []
    for param in ET.parse(config_path).getroot().iter('param'):
        value = (param.get('value') or '').strip()
        if not value or Path(value).is_absolute():
            continue
        candidate = base_dir / value
        if candidate.is_file():
            if base_dir.resolve() not in candidate.resolve().parents:
                logger.warning(f"config.xml names a file outside the base folder; "
                               f"not copied: {value}")
                continue
            names.append(value)
    return sorted(set(names))


def _link_or_copy(src: Path, dst: Path) -> None:
    """Hard-link an input file, or copy it where links are not possible.

    MATSim only reads these files, and plans.xml alone can be gigabytes, so a
    link saves the disk space of a second copy.
    """
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _transit_route_links(config_path: Path) -> set:
    """Link IDs that a transit line drives on, from the transit schedule."""
    name = _config_param(config_path, 'transit', 'transitScheduleFile')
    if (_config_param(config_path, 'transit', 'useTransit') or '').lower() != 'true' or not name:
        return set()
    path = config_path.parent / name
    if not path.is_file():
        return set()
    pattern = re.compile(r'<link\s+refId="([^"]+)"')
    used = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            if 'refId' in line:
                used.update(pattern.findall(line))
    return used


def scenario_run_dir(base_dir: Path, scenario: Scenario,
                     experiments_root: Optional[Path] = None) -> Path:
    root = Path(experiments_root) if experiments_root else base_dir.parent
    return root / f"{base_dir.name}__{scenario.name}"


def prepare_scenario(base_dir: Path, scenario_path: Path,
                     experiments_root: Optional[Path] = None) -> Path:
    """Check everything, make the scenario folder and the closed network.

    All checks run before the folder is made, so a bad scenario file leaves
    nothing behind.
    """
    base_dir = Path(base_dir).resolve()
    scenario = load_scenario(scenario_path)

    config_path = base_dir / 'config.xml'
    if not config_path.is_file():
        raise ScenarioError(f"No config.xml in the base folder: {base_dir}")
    if scenario.base_experiment != base_dir.name:
        raise ScenarioError(
            f"The scenario was made from '{scenario.base_experiment}', "
            f"but --base is '{base_dir.name}'. Link IDs only match the run they came from.")

    network_name = network_file_name(config_path)
    base_network = base_dir / network_name
    if not base_network.is_file():
        raise ScenarioError(f"Base network not found: {base_network}")

    run_dir = scenario_run_dir(base_dir, scenario, experiments_root)
    if run_dir.exists():
        raise ScenarioError(
            f"The scenario folder already exists: {run_dir}. "
            "Delete it, or give the scenario a new name.")

    logger.info(f"Reading base network: {base_network}")
    links, _ = read_network(base_network)
    requested = scenario.closed_link_ids
    unknown = [l for l in requested if l not in links]
    if unknown:
        raise ScenarioError(
            f"{len(unknown)} link ID(s) are not in the base network: {unknown[:10]}")
    no_car = [l for l in requested if CAR not in links[l].modes]
    if no_car:
        raise ScenarioError(
            f"{len(no_car)} link(s) do not allow cars, so they cannot be closed: {no_car[:10]}")

    cut_off = find_cut_off_links(links, requested)
    all_closed = requested + cut_off
    car_links = sum(1 for info in links.values() if CAR in info.modes)
    logger.info(f"Closing {len(requested)} selected link(s) and "
                f"{len(cut_off)} cut-off link(s) of {car_links:,} car links")
    if cut_off and len(cut_off) > 0.01 * car_links:
        logger.warning(f"The closure cuts off {len(cut_off):,} car links "
                       f"({100 * len(cut_off) / car_links:.1f}% of the car network). "
                       "Check the selected links: this is more than a dead-end stretch.")

    still_open = {}
    for link_id in all_closed:
        kept = [m for m in modes_after_closure(links[link_id].modes) if m != CLOSED_MODE]
        if kept:
            still_open[link_id] = kept
    # Bus lines are fixed lists of links, so they still drive through the
    # closure. Name the closed links a line actually uses.
    transit_links = _transit_route_links(config_path)
    used_by_transit = [l for l in all_closed if l in transit_links]
    if used_by_transit:
        logger.warning(f"{len(used_by_transit)} closed link(s) are on transit lines; "
                       "buses still drive on them")

    run_dir.mkdir(parents=True)
    log_path = reconfigure_logger_to_experiment_dir(run_dir, log_prefix='scenario')
    logger.info(f"Scenario folder: {run_dir}")
    logger.info(f"Log: {log_path}")

    shutil.copy2(config_path, run_dir / 'config.xml')
    copied = ['config.xml']
    for name in _input_files(config_path):
        if name == network_name:
            continue
        (run_dir / name).parent.mkdir(parents=True, exist_ok=True)
        _link_or_copy(base_dir / name, run_dir / name)
        copied.append(name)
    for name in EXTRA_FILES:
        if (base_dir / name).is_file():
            shutil.copy2(base_dir / name, run_dir / name)
            copied.append(name)
    logger.info(f"Copied from the base run: {', '.join(copied)}")

    changed = write_closed_network(base_network, run_dir / network_name, all_closed)
    logger.info(f"Wrote {network_name} with {changed} closed link(s)")

    with open(run_dir / SCENARIO_COPY, 'w', encoding='utf-8') as f:
        json.dump(scenario.raw, f, indent=2)

    summary = {
        'scenario': scenario.name,
        'description': scenario.description,
        'base_experiment': base_dir.name,
        'base_dir': str(base_dir),
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'closed_links': {
            'selected': requested,
            'cut_off': cut_off,
            'still_open_to': still_open,
            'used_by_transit': used_by_transit,
        },
        'files_copied': copied,
        'simulation_status': 'not_run',
    }
    _write_summary(run_dir, summary)
    return run_dir


def _json_default(value):
    # Evaluation metrics come back as numpy scalars.
    if hasattr(value, 'item'):
        return value.item()
    return str(value)


def _write_summary(run_dir: Path, summary: Dict) -> None:
    with open(run_dir / SUMMARY_FILE, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, default=_json_default)


def read_summary(run_dir: Path) -> Dict:
    path = Path(run_dir) / SUMMARY_FILE
    if not path.is_file():
        raise ScenarioError(f"Not a scenario run (no {SUMMARY_FILE}): {run_dir}")
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _run_evaluation(run_dir: Path, config: Dict) -> Optional[Dict]:
    """The normal count evaluation, as run_experiment.py runs it."""
    evaluation_config = config.get('evaluation', {})
    if not evaluation_config.get('run_evaluation', True):
        return None
    if not config.get('counts', {}).get('enabled', True):
        return None
    if not (run_dir / 'matched_devices.csv').is_file():
        logger.info("No matched_devices.csv: count evaluation skipped")
        return None
    data_dir = Path(evaluation_config.get('ground_truth_data_dir', 'data/evaluation'))
    if not data_dir.exists():
        logger.info(f"Ground truth folder not found ({data_dir}): count evaluation skipped")
        return None
    from matsim.evaluator import SimulationEvaluator
    try:
        evaluator = SimulationEvaluator(experiment_dir=run_dir, ground_truth_data_dir=data_dir)
        _, metrics = evaluator.run_evaluation(
            generate_spatial_maps=evaluation_config.get('generate_spatial_maps', True),
            generate_per_device_reports=evaluation_config.get('generate_per_device_reports', False))
        if metrics.get('error'):
            # A block of zeros with an 'error' key means no input, not a result.
            logger.info(f"Count evaluation has no input: {metrics['error']}")
            return None
        return metrics
    except Exception as e:
        logger.warning(f"Count evaluation failed; the scenario run itself is fine: {e}")
        return None


def run_simulation(run_dir: Path) -> Dict:
    """Run MATSim on a prepared scenario folder, then the count evaluation."""
    from matsim.orchestrator import MATSimOrchestrator

    run_dir = Path(run_dir).resolve()
    summary = read_summary(run_dir)
    config_used = run_dir / 'config_used.json'
    if not config_used.is_file():
        raise ScenarioError(f"No config_used.json in {run_dir}: the base run is incomplete")
    with open(config_used, encoding='utf-8') as f:
        config = json.load(f)

    started = datetime.now()
    orchestrator = MATSimOrchestrator(config_dict=config, experiments_root=run_dir.parent)
    process = orchestrator.run_experiment(run_dir, blocking=True)
    return_code = getattr(process, 'returncode', None)
    summary['simulation_status'] = 'completed' if return_code in (0, None) else 'failed'
    summary['matsim_return_code'] = return_code
    summary['matsim_minutes'] = round((datetime.now() - started).total_seconds() / 60, 1)
    _write_summary(run_dir, summary)
    if summary['simulation_status'] != 'completed':
        raise RuntimeError(f"MATSim exited with code {return_code}; "
                           f"see {run_dir / 'matsim_output.log'}")

    metrics = _run_evaluation(run_dir, config)
    if metrics is not None:
        summary['evaluation'] = metrics
        _write_summary(run_dir, summary)
    return summary
