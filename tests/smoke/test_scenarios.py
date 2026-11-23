# SPDX-License-Identifier: GPL-3.0-or-later
"""What-If Scenarios: the scenario file, closing links, the cut-off check."""

import pytest

from scenarios.definition import ScenarioError, load_scenario, parse_scenario
from scenarios.network import (CLOSED_MODE, find_cut_off_links, modes_after_closure,
                               read_network, write_closed_network)

pytestmark = pytest.mark.smoke

# A small car network: a two-way main road A-B-C-D, plus a one-way spur
# B->E->C that is only usable because it rejoins the main road.
#
#   A <-> B <-> C <-> D
#         \-> E ->/
NETWORK = """<?xml version='1.0' encoding='UTF-8'?>
<!DOCTYPE network SYSTEM "http://www.matsim.org/files/dtd/network_v2.dtd">
<network>
\t<nodes>
\t\t<node id="A" x="0.0" y="0.0">
\t\t</node>
\t\t<node id="B" x="100.0" y="0.0">
\t\t</node>
\t\t<node id="C" x="200.0" y="0.0">
\t\t</node>
\t\t<node id="D" x="300.0" y="0.0">
\t\t</node>
\t\t<node id="E" x="150.0" y="50.0">
\t\t</node>
\t</nodes>
\t<links capperiod="01:00:00" effectivecellsize="7.5" effectivelanewidth="3.75">
\t\t<link id="1" from="A" to="B" length="100.0" freespeed="10.0" capacity="600.0" permlanes="1.0" oneway="1" modes="car">
\t\t\t<attributes>
\t\t\t\t<attribute name="osm:way:highway" class="java.lang.String">primary</attribute>
\t\t\t\t<attribute name="osm:way:name" class="java.lang.String">Main Street</attribute>
\t\t\t</attributes>
\t\t</link>
\t\t<link id="2" from="B" to="A" length="100.0" freespeed="10.0" capacity="600.0" permlanes="1.0" oneway="1" modes="car">
\t\t</link>
\t\t<link id="3" from="B" to="C" length="100.0" freespeed="10.0" capacity="600.0" permlanes="1.0" oneway="1" modes="bus,car">
\t\t</link>
\t\t<link id="4" from="C" to="B" length="100.0" freespeed="10.0" capacity="600.0" permlanes="1.0" oneway="1" modes="bus,car">
\t\t</link>
\t\t<link id="5" from="C" to="D" length="100.0" freespeed="10.0" capacity="600.0" permlanes="1.0" oneway="1" modes="car">
\t\t</link>
\t\t<link id="6" from="D" to="C" length="100.0" freespeed="10.0" capacity="600.0" permlanes="1.0" oneway="1" modes="car">
\t\t</link>
\t\t<link id="7" from="B" to="E" length="80.0" freespeed="10.0" capacity="600.0" permlanes="1.0" oneway="1" modes="car">
\t\t</link>
\t\t<link id="8" from="E" to="C" length="80.0" freespeed="10.0" capacity="600.0" permlanes="1.0" oneway="1" modes="car">
\t\t</link>
\t</links>
</network>
"""


@pytest.fixture
def network(tmp_path):
    path = tmp_path / 'network.xml'
    path.write_text(NETWORK, encoding='utf-8')
    return path


def _scenario(**overrides):
    data = {'name': 'test_closure', 'base_experiment': 'exp_1',
            'closures': [{'type': 'close', 'link_ids': ['5', '6']}]}
    data.update(overrides)
    return data


def test_parse_valid_scenario():
    s = parse_scenario(_scenario(description='x', _help='comment'))
    assert s.name == 'test_closure'
    assert s.closed_link_ids == ['5', '6']


def test_link_ids_are_deduplicated_and_numbers_accepted():
    s = parse_scenario(_scenario(closures=[{'type': 'close', 'link_ids': [5, '6', '5']}]))
    assert s.closed_link_ids == ['5', '6']


@pytest.mark.parametrize('overrides', [
    {'name': 'bad name'},
    {'name': ''},
    {'base_experiment': ''},
    {'closures': []},
    {'closures': [{'type': 'reduce_lanes', 'link_ids': ['1']}]},
    {'closures': [{'type': 'close', 'link_ids': []}]},
    {'closures': [{'type': 'close', 'link_ids': [None]}]},
])
def test_bad_scenarios_are_rejected(overrides):
    with pytest.raises(ScenarioError):
        parse_scenario(_scenario(**overrides))


def test_load_scenario_reports_bad_json(tmp_path):
    path = tmp_path / 's.json'
    path.write_text('{not json', encoding='utf-8')
    with pytest.raises(ScenarioError):
        load_scenario(path)


def test_read_network_keeps_names_and_modes(network):
    links, nodes = read_network(network)
    assert len(links) == 8 and len(nodes) == 5
    assert links['1'].name == 'Main Street'
    assert links['1'].highway == 'primary'
    assert links['3'].modes == frozenset({'bus', 'car'})


def test_modes_after_closure():
    assert modes_after_closure(['bus', 'car']) == ['bus']
    assert modes_after_closure(['car']) == [CLOSED_MODE]


def test_closing_a_through_road_cuts_nothing_off(network):
    links, _ = read_network(network)
    # Closing B->C leaves the spur B->E->C as the way east.
    assert find_cut_off_links(links, ['3']) == []


def test_closing_the_end_of_a_road_cuts_off_the_dead_end(network):
    links, _ = read_network(network)
    # With C->D and D->C closed, D is unreachable; nothing else is cut off.
    assert find_cut_off_links(links, ['5', '6']) == []
    # With the spur exit E->C closed, B->E becomes a dead end.
    assert find_cut_off_links(links, ['8']) == ['7']


def test_write_closed_network_changes_only_closed_links(network, tmp_path):
    out = tmp_path / 'closed.xml'
    assert write_closed_network(network, out, ['3', '5']) == 2
    links, _ = read_network(out)
    assert links['3'].modes == frozenset({'bus'})
    assert links['5'].modes == frozenset({CLOSED_MODE})
    assert links['1'].modes == frozenset({'car'})
    # Everything except the two modes attributes is unchanged.
    before = network.read_text(encoding='utf-8').splitlines()
    after = out.read_text(encoding='utf-8').splitlines()
    assert len(before) == len(after)
    assert sum(a != b for a, b in zip(before, after)) == 2


def test_write_closed_network_fails_on_unknown_link(network, tmp_path):
    with pytest.raises(ValueError):
        write_closed_network(network, tmp_path / 'closed.xml', ['999'])


# --- Road tables in the compare report -------------------------------------

def _road_case():
    """Links for the road-table tests, with their daily change.

    - 'Main Street' in two towns 10 km apart: two roads.
    - 'Oak Avenue': a divided road, two one-way sides 40 m apart that share no
      node, each 1 km: one road, 1 km long.
    - An unnamed motorway, two links in a row: one road, in the table.
    - An unnamed roundabout ring whose links have two road types: one road.
    """
    import pandas as pd
    from scenarios.network import LinkInfo

    nodes = {
        'a1': (0, 0), 'a2': (500, 0), 'b1': (10000, 0), 'b2': (10500, 0),
        'o1': (0, 2000), 'o2': (1000, 2000), 'o3': (1000, 2040), 'o4': (0, 2040),
        'm1': (0, 5000), 'm2': (0, 6000), 'm3': (0, 7000),
        'r1': (3000, 3000), 'r2': (3020, 3000), 'r3': (3010, 3020),
    }
    rows = [  # id, from, to, name, type, junction, change
        ('1', 'a1', 'a2', 'Main Street', 'residential', '', 900),
        ('2', 'a2', 'a1', 'Main Street', 'residential', '', 850),
        ('3', 'b1', 'b2', 'Main Street', 'residential', '', 400),
        ('4', 'o1', 'o2', 'Oak Avenue', 'primary', '', 700),
        ('5', 'o3', 'o4', 'Oak Avenue', 'primary', '', 650),
        ('6', 'm1', 'm2', '', 'motorway', '', 2000),
        ('7', 'm2', 'm3', '', 'motorway', '', 1900),
        ('8', 'r1', 'r2', '', 'secondary', 'roundabout', 300),
        ('9', 'r2', 'r3', '', 'tertiary', 'roundabout', 280),
        ('10', 'r3', 'r1', '', 'tertiary', 'roundabout', 290),
    ]
    links = {}
    for link_id, a, b, name, rtype, junction, _ in rows:
        (xa, ya), (xb, yb) = nodes[a], nodes[b]
        links[link_id] = LinkInfo(from_node=a, to_node=b, modes=frozenset({'car'}),
                                  length=float(((xb - xa) ** 2 + (yb - ya) ** 2) ** 0.5),
                                  highway=rtype, name=name, junction=junction)
    df = pd.DataFrame({
        'link_id': [r[0] for r in rows],
        'name': [r[3] for r in rows],
        'road_type': [r[4] for r in rows],
        'length_m': [links[r[0]].length for r in rows],
        'closed': '',
        'low_volume': False,
        'daily_before': 1000.0,
        'change': [float(r[6]) for r in rows],
    })
    df['change_pct'] = 100.0 * df['change'] / df['daily_before']
    return df, links, nodes


def test_road_geometry_groups_links_into_roads():
    from scenarios.compare import road_geometry
    df, links, nodes = _road_case()
    road = road_geometry(df, links, nodes).set_index(df['link_id'])['road']
    assert road['1'] == road['2'] != road['3']       # same name, two towns
    assert road['4'] == road['5']                    # two sides of a divided road
    assert road['6'] == road['7']                    # unnamed motorway in a row
    assert road['8'] == road['9'] == road['10']      # one roundabout ring
    assert road.nunique() == 5


def test_road_table_shows_unnamed_roads_and_counts_one_direction():
    from scenarios.compare import _road_table, road_geometry
    df, links, nodes = _road_case()
    lines = _road_table(df, road_geometry(df, links, nodes), gained=True)
    rows = {line.split(' | ')[0].lstrip('| '): line.split(' | ') for line in lines[2:]}
    assert len(rows) == 5
    motorway = [r for name, r in rows.items() if name.startswith('(no name)')]
    assert len(motorway) == 1 and motorway[0][-1].strip(' |') == '6'
    assert any(name.startswith('(roundabout)') for name in rows)
    # The two Main Streets are two rows, told apart by a nearby road.
    assert sum(name.startswith('Main Street, near ') for name in rows) == 2
    # Oak Avenue: two 1 km sides, counted once.
    assert rows['Oak Avenue'][5] == '1.0'
