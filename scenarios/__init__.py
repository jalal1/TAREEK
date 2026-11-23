# SPDX-License-Identifier: GPL-3.0-or-later
"""What-If Scenarios: run a finished baseline again with roads closed.

See scenarios/README.md. Entry point: run_scenario.py.
"""

from scenarios.definition import Closure, Scenario, ScenarioError, load_scenario

__all__ = ['Closure', 'Scenario', 'ScenarioError', 'load_scenario']
