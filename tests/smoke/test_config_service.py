"""Pure configuration tests: no data downloads, DB, Java or web startup."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from webapp.backend.config_service import (
    ConfigService, ConfigurationError, deep_merge, user_config, validate_structure,
)

pytestmark = pytest.mark.smoke
ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / 'examples').glob('*/config_used.json'))


def assert_preserved(original, actual):
    """Every original leaf survives, including complete arrays and annotations."""
    if isinstance(original, dict):
        for key, value in original.items():
            assert key in actual
            assert_preserved(value, actual[key])
    else:
        assert actual == original


@pytest.mark.parametrize('path', EXAMPLES, ids=lambda p: p.parent.name)
def test_all_examples_preserved(path):
    source_bytes = path.read_bytes()
    original = json.loads(source_bytes)
    result = ConfigService(ROOT).load_example(path.parent.name)
    expected = deepcopy(original)
    expected.pop('_config_dir', None)
    expected.pop('_demand_budget', None)
    expected['coordinates'].pop('utm_epsg', None)
    expected['matsim'].pop('_survey_typical_durations', None)
    expected['matsim'].pop('_survey_activity_params', None)
    assert_preserved(expected, result.config)
    assert result.config['freight'] == original['freight']
    assert result.config['data']['surveys'] == original['data']['surveys']
    assert 'scale_transit_pce' not in result.config['matsim']
    assert any(i['path'] == 'matsim.scale_transit_pce' for i in result.issues)
    assert result.config['network']['roundabout_capacity_per_lane'] is None
    assert path.read_bytes() == source_bytes
    # The web preparation path must retain exactly the same configuration.
    assert ConfigService(ROOT).assemble({'example_id': path.parent.name}).config == result.config


def test_baseline_is_maintained_source_and_independent():
    path = ROOT / 'config/config_local.json'
    source = path.read_bytes()
    service = ConfigService(ROOT)
    first = service.load_baseline()
    assert first.config == user_config(json.loads(source))
    first.config['data']['surveys'].clear()
    assert service.load_baseline().config['data']['surveys']
    assert path.read_bytes() == source


def test_deep_merge_replaces_arrays_and_copies_inputs():
    base = {'nested': {'keep': 1, 'array': [{'old': 1}, 2]}, 'other': 3}
    patch = {'nested': {'array': [{'new': 2}]}}
    result = deep_merge(base, patch)
    assert result == {'nested': {'keep': 1, 'array': [{'new': 2}]}, 'other': 3}
    result['nested']['array'][0]['new'] = 9
    assert patch['nested']['array'][0]['new'] == 2
    assert base['nested']['array'] == [{'old': 1}, 2]
    assert deep_merge(base, {'nested': None})['nested'] is None


def test_edit_keeps_hidden_engine_options_and_paths():
    service = ConfigService(ROOT)
    original = service.load_example('chicago-20261003').config
    result = service.assemble({'example_id': 'chicago-20261003', 'overrides': {
        'freight': {'demand_scale': 0.25},
        'matsim': {'configurable_params': {'lastIteration': 2}},
    }})
    expected = deepcopy(original)
    expected['freight']['demand_scale'] = 0.25
    expected['matsim']['configurable_params']['lastIteration'] = 2
    assert result.config == expected
    assert any(i['code'] == 'absolute_path' for i in result.issues)
    assert any(i['code'] == 'machine_resource' for i in result.issues)


def test_legacy_wizard_and_unknown_parameters():
    service = ConfigService(ROOT)
    surveys = [{'type': 'custom', 'weight': 1, 'roles': {'person_days': 1}}]
    result = service.assemble({'counties': ['06037'], 'surveys': surveys,
                               'new_engine_feature': {'enabled': True}})
    assert result.config['region']['counties'] == ['06037']
    assert result.config['data']['surveys'] == surveys
    assert result.config['new_engine_feature'] == {'enabled': True}
    assert result.config['matsim']['scale_transit_pce'] is True


def test_migrations_are_idempotent_and_do_not_infer_behavior():
    service = ConfigService(ROOT)
    config = service.load_baseline().config
    config['network']['counties'] = config.pop('region')['counties']
    config['network'].pop('roundabout_capacity_per_lane')
    config['matsim'].pop('scale_transit_pce')
    first = service.prepare(config, historical=True)
    second = service.prepare(first.config, historical=True)
    assert len(first.migrations) == 2
    assert second.migrations == []
    assert first.config == second.config
    assert 'scale_transit_pce' not in first.config['matsim']


def test_generated_fields_only_are_removed():
    config = ConfigService(ROOT).load_baseline().config
    config.update(_config_dir='/old', _demand_budget={'old': True}, _custom_extension=42)
    config['matsim'].update(_survey_typical_durations={'Work': 42},
                            _survey_activity_params={}, _comment='keep')
    result = user_config(config)
    assert '_config_dir' not in result and '_demand_budget' not in result
    assert '_survey_typical_durations' not in result['matsim']
    assert '_survey_activity_params' not in result['matsim']
    assert result['_custom_extension'] == 42
    assert result['matsim']['_comment'] == 'keep'
    assert config['_config_dir'] == '/old'


def test_structural_checks_do_not_require_execution_host(tmp_path):
    service = ConfigService(ROOT)
    config = service.load_baseline().config
    config['data']['data_dir'] = str(tmp_path / 'absent')
    before = deepcopy(config)
    validate_structure(config)
    issues = service.check_execution_readiness(config, tmp_path / 'config.json')
    assert any(i['code'] == 'missing_data_dir' for i in issues)
    assert config == before


@pytest.mark.parametrize('payload', [[], {'overrides': []}, {'region': None},
    {'config': []}, {'example_id': '../config'},
    {'example_id': 'chicago-20261003', 'config': {}}])
def test_invalid_requests(payload):
    with pytest.raises(ConfigurationError):
        ConfigService(ROOT).assemble(payload)


def test_invalid_structure():
    config = ConfigService(ROOT).load_baseline().config
    config['data']['surveys'] = 'not an array'
    with pytest.raises(ConfigurationError, match='surveys'):
        validate_structure(config)


def test_backend_export_and_diagnostic_contract():
    import asyncio
    from webapp.backend.main import export_config, prepare_config, get_default_config

    class Request:
        async def json(self):
            return {'example_id': 'birmingham-localsurvey-20261001'}

    response = asyncio.run(export_config(Request()))
    config = json.loads(response.body)
    assert config['freight']['enabled'] is True
    assert config['data']['surveys'][1]['roles'] == {'person_days': 1}
    assert json.loads(response.headers['x-config-issues'])
    diagnostic = asyncio.run(prepare_config(Request()))
    assert diagnostic['config'] == config
    assert diagnostic['issues'] == json.loads(response.headers['x-config-issues'])
    assert get_default_config() == ConfigService(ROOT).load_baseline().config


def test_backend_rejects_invalid_export():
    import asyncio
    from fastapi import HTTPException
    from webapp.backend.main import export_config

    class Request:
        async def json(self):
            return []

    with pytest.raises(HTTPException) as error:
        asyncio.run(export_config(Request()))
    assert error.value.status_code == 422
