#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""What-If Scenarios: run a finished baseline again with roads closed.

The scenario file comes from TAREEK-Vis (Selected links -> Export scenario
file). See scenarios/README.md.

Examples:
  # Close the links, run MATSim, then write the compare report
  python run_scenario.py run --base experiments/<baseline> --scenario hwy15_closure.json

  # Only make the scenario folder and the closed network (no MATSim)
  python run_scenario.py run --base experiments/<baseline> --scenario hwy15_closure.json --prepare-only

  # (Re)write the compare report of a finished scenario run
  python run_scenario.py compare --base experiments/<baseline> --scenario-run experiments/<baseline>__hwy15_closure
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scenarios.definition import ScenarioError
from utils.logger import setup_logger

logger = setup_logger(__name__)


def cmd_run(args) -> int:
    from scenarios.compare import compare
    from scenarios.run import prepare_scenario, run_simulation

    run_dir = prepare_scenario(
        Path(args.base), Path(args.scenario),
        experiments_root=Path(args.experiments_root) if args.experiments_root else None)
    if args.prepare_only:
        logger.info(f"Prepared (MATSim not run): {run_dir}")
        logger.info(f"To run it later: python run_scenario.py resume --scenario-run {run_dir}")
        return 0
    run_simulation(run_dir)
    report = compare(Path(args.base), run_dir)
    logger.info(f"Scenario run: {run_dir}")
    logger.info(f"Compare report: {report}")
    return 0


def cmd_resume(args) -> int:
    from scenarios.compare import compare
    from scenarios.run import run_simulation

    run_dir = Path(args.scenario_run)
    summary = run_simulation(run_dir)
    report = compare(Path(summary['base_dir']), run_dir)
    logger.info(f"Compare report: {report}")
    return 0


def cmd_compare(args) -> int:
    from scenarios.compare import compare

    report = compare(Path(args.base), Path(args.scenario_run))
    logger.info(f"Compare report: {report}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Run a finished baseline again with roads closed, and compare the two.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split('Examples:', 1)[1] if 'Examples:' in __doc__ else None)
    sub = parser.add_subparsers(dest='command', required=True)

    p_run = sub.add_parser('run', help='Make the scenario folder, run MATSim, write the report')
    p_run.add_argument('--base', required=True, help='Folder of the finished baseline run')
    p_run.add_argument('--scenario', required=True, help='Scenario JSON file (from TAREEK-Vis)')
    p_run.add_argument('--experiments-root', default=None,
                       help='Where to make the scenario folder (default: next to the baseline)')
    p_run.add_argument('--prepare-only', action='store_true',
                       help='Make the folder and the closed network, but do not run MATSim')
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser('resume', help='Run MATSim on a folder made with --prepare-only')
    p_resume.add_argument('--scenario-run', required=True, help='The scenario run folder')
    p_resume.set_defaults(func=cmd_resume)

    p_cmp = sub.add_parser('compare', help='Write the compare report of a finished scenario run')
    p_cmp.add_argument('--base', required=True, help='Folder of the baseline run')
    p_cmp.add_argument('--scenario-run', required=True, help='Folder of the scenario run')
    p_cmp.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    try:
        sys.exit(args.func(args))
    except ScenarioError as e:
        logger.error(str(e))
        sys.exit(2)
    except Exception as e:
        logger.error(f"Scenario failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
