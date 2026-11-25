# SPDX-License-Identifier: GPL-3.0-or-later
"""Every leg mode in plans.xml gets a modeParams block (P5).

With modes.bike enabled, a plan could get a bike leg and MATSim stopped with
"no scoring parameters are defined: bike". The pre-flight check that already
reads plans.xml for activity types now also adds a modeParams block for each
leg mode that has none.
"""

import xml.etree.ElementTree as ET

import pytest

from matsim.config_manager import ConfigManager

SCORING = """
<parameterset type="scoringParameters">
  <parameterset type="activityParams"><param name="activityType" value="Home"/></parameterset>
  <parameterset type="activityParams"><param name="activityType" value="Work"/></parameterset>
  <parameterset type="modeParams"><param name="mode" value="car"/></parameterset>
  <parameterset type="modeParams"><param name="mode" value="walk"/></parameterset>
</parameterset>
"""

PLANS = """<population>
<person id="1"><plan selected="yes">
  <activity type="Home" x="0" y="0" end_time="07:00:00"/>
  <leg mode="bike"/>
  <activity type="Work" x="1" y="1" max_dur="08:00:00"/>
  <leg mode="car"/>
  <activity type="Home" x="0" y="0"/>
</plan></person>
</population>
"""


@pytest.mark.smoke
def test_missing_leg_mode_gets_a_modeparams_block(tmp_path):
    plans = tmp_path / 'plans.xml'
    plans.write_text(PLANS)
    scoring = ET.fromstring(SCORING)
    cm = ConfigManager.__new__(ConfigManager)
    cm._get_scoring_parameterset = lambda tree: scoring

    cm.verify_activity_params_cover_plans(tree=None, plans_path=plans)

    modes = [p.find("param[@name='mode']").get('value')
             for p in scoring.findall("parameterset[@type='modeParams']")]
    assert sorted(modes) == ['bike', 'car', 'walk']


@pytest.mark.smoke
def test_booleans_are_written_lowercase():
    """MATSim rejects "True" ("Incorrect value of the boolean parameter")."""
    from matsim.config_manager import _xml_value
    assert _xml_value(True) == 'true'
    assert _xml_value(False) == 'false'
    assert _xml_value(0.15) == '0.15'
    assert _xml_value('36:00:00') == '36:00:00'
