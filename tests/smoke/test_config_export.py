"""Export an authoritative loaded configuration without reconstructing it."""
import asyncio
from copy import deepcopy
import json

import pytest
from fastapi import HTTPException

from webapp.backend import main
from webapp.backend.config_service import ConfigService
from webapp.backend.preset_service import PRESETS

pytestmark = pytest.mark.smoke


def export(payload):
    class Request:
        async def json(self):
            return deepcopy(payload)

    response = asyncio.run(main.export_config(Request()))
    return json.loads(response.body), response.headers


def la_preset():
    return asyncio.run(main.get_config_preset('losangeles-20261006'))['config']


@pytest.mark.parametrize('preset_id', PRESETS)
def test_every_preset_review_export_and_source_integrity(preset_id):
    root = main.config_service.root
    sources = [root / 'config/config_local.json',
               *sorted((root / 'examples').glob('*/config_used.json'))]
    before = {path: path.read_bytes() for path in sources}
    loaded = asyncio.run(main.get_config_preset(preset_id))['config']

    class ReviewRequest:
        async def json(self):
            return {'config': deepcopy(loaded)}

    review = asyncio.run(main.prepare_config(ReviewRequest()))
    exported, _ = export(loaded)
    assert review['config'] == exported == loaded
    assert exported['freight'] == loaded['freight']
    assert exported['matsim']['configurable_params'] == loaded['matsim']['configurable_params']
    assert {path: path.read_bytes() for path in sources} == before


def test_la_load_and_export_is_lossless(monkeypatch):
    config = la_preset()
    original = deepcopy(config)
    # Full-config export must not load any baseline or re-read a preset.
    def forbidden(*args):
        raise AssertionError('Authoritative configuration must not load defaults')
    monkeypatch.setattr(main.config_service, 'load_baseline', forbidden)
    monkeypatch.setattr(main.config_service, 'load_example', forbidden)
    exported, _ = export(config)
    assert exported == original
    assert config == original
    assert exported['freight'] == original['freight']
    params = exported['matsim']['configurable_params']
    assert params == original['matsim']['configurable_params']
    assert params['controller.mobsim'] == 'hermes'
    assert 'transitRouter.searchRadius' in params
    assert exported['matsim']['heap_size_gb'] == 200


def test_one_edit_changes_only_that_value():
    original = la_preset()
    changed = deepcopy(original)
    changed['matsim']['configurable_params']['lastIteration'] = 7
    exported, _ = export(changed)
    assert exported == changed
    exported['matsim']['configurable_params']['lastIteration'] = original['matsim']['configurable_params']['lastIteration']
    assert exported == original


def test_future_baseline_fields_and_json_values_survive(tmp_path, monkeypatch):
    service = ConfigService(tmp_path)
    baseline = main.config_service.load_baseline().config
    baseline['future_feature'] = {
        'enabled': False, 'optional': None,
        'entries': [{'a': 1}, None, True, False, ['nested']],
        'nested': {'engine.key.with.periods': 3},
    }
    (tmp_path / 'config').mkdir()
    source = tmp_path / 'config/config_local.json'
    source.write_text(json.dumps(baseline))
    before = source.read_bytes()
    loaded = service.load_baseline().config
    monkeypatch.setattr(main, 'config_service', service)
    exported, _ = export(loaded)
    assert exported == loaded
    assert source.read_bytes() == before


def test_export_only_removes_known_runtime_fields():
    config = la_preset()
    config['_extension'] = {'custom': True}
    expected = deepcopy(config)
    config['_config_dir'] = '/old/machine'
    config['_demand_budget'] = {'old': True}
    config['matsim']['_survey_typical_durations'] = {'Work': 100}
    config['matsim']['_survey_activity_params'] = {'Work': {}}
    config['coordinates']['utm_epsg'] = 'EPSG:26911'
    assert export(config)[0] == expected


@pytest.mark.parametrize('edit, error', [
    (lambda c: c.pop('network'), 'network must be an object'),
    (lambda c: c['data'].update(surveys={}), 'data.surveys'),
    (lambda c: c['region'].update(counties=[]), 'counties'),
    (lambda c: c['freight'].update(enabled='false'), 'freight.enabled'),
    (lambda c: c['plan_generation'].update(scaling_factor=-1), 'scaling_factor'),
    (lambda c: c['matsim'].update(configurable_params=[]), 'configurable_params'),
    (lambda c: c['matsim']['configurable_params'].update(lastIteration=-1), 'lastIteration'),
    (lambda c: c['matsim'].update(mode='invalid'), 'matsim.mode'),
    (lambda c: c['matsim']['configurable_params'].update({'qsim.flowCapacityFactor': 0}), 'qsim.flowCapacityFactor'),
])
def test_invalid_configuration_has_useful_errors(edit, error):
    config = la_preset()
    edit(config)
    with pytest.raises(HTTPException) as exc:
        export(config)
    assert exc.value.status_code == 422
    assert error in exc.value.detail


@pytest.mark.parametrize('payload', [{}, [], {'config': None}, {'example_id': None}])
def test_invalid_input_never_falls_back_to_baseline(payload):
    with pytest.raises(HTTPException) as exc:
        export(payload)
    assert exc.value.status_code == 422


def test_legacy_payload_is_explicitly_deprecated():
    config, headers = export({'counties': ['06037'], 'surveys': []})
    assert config['region']['counties'] == ['06037']
    assert headers['x-config-input-format'] == 'legacy-wizard; deprecated'
    assert any(i['code'] == 'legacy_export_payload' for i in json.loads(headers['x-config-issues']))


def test_existing_config_edit_envelope():
    original = la_preset()
    config, _ = export({'config': original, 'overrides': {'freight': {'demand_scale': 0.2}}})
    expected = deepcopy(original)
    expected['freight']['demand_scale'] = 0.2
    assert config == expected


def test_invalid_json():
    class Request:
        async def json(self):
            raise ValueError('bad JSON')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.export_config(Request()))
    assert exc.value.status_code == 400
    assert exc.value.detail == 'Invalid JSON body'
