"""Exercise real FastAPI routing without startup downloads or an HTTP client dependency."""
import asyncio
from copy import deepcopy
import json

import pytest

from webapp.backend import main
from webapp.backend.config_service import ConfigService
from webapp.backend.preset_service import PRESETS, public_config

pytestmark = pytest.mark.smoke


def get(path):
    async def request():
        messages = []

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        async def send(message):
            messages.append(message)

        await main.app({'type': 'http', 'asgi': {'version': '3.0'},
                        'http_version': '1.1', 'method': 'GET', 'scheme': 'http',
                        'path': path, 'raw_path': path.encode(), 'query_string': b'',
                        'root_path': '', 'headers': [], 'server': ('test', 80),
                        'client': ('test', 123)}, receive, send)
        status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
        body = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
        return status, json.loads(body)

    return asyncio.run(request())


def test_list_metadata_and_variants():
    status, response = get('/api/config/presets')
    assert status == 200
    presets = response['presets']
    assert {p['id'] for p in presets} == set(PRESETS)
    assert {p['region'] for p in presets} == {
        'Los Angeles', 'New York', 'Madison', 'Chicago', 'Twin Cities', 'Birmingham'}
    twins = [p for p in presets if p['region'] == 'Twin Cities']
    assert len(twins) == 2
    for preset in presets:
        assert all(preset[k] for k in ('id', 'display_name', 'region', 'description', 'source_file'))
        assert -90 <= preset['location']['lat'] <= 90
        assert -180 <= preset['location']['lng'] <= 180
        assert 'config' not in preset
        assert preset['characteristics']['surveys']
        assert preset['warnings']


@pytest.mark.parametrize('preset_id', PRESETS)
def test_detail_preserves_complete_normalized_configuration(preset_id):
    status, response = get('/api/config/presets/' + preset_id)
    assert status == 200
    expected = main.config_service.load_example(preset_id).config
    safe, _ = public_config(expected)
    assert response['location'] == dict(zip(('lat', 'lng'), PRESETS[preset_id]['location']))
    assert response['config'] == safe
    # Scientific settings are unaffected by credential handling.
    for section in ('freight', 'matsim', 'region', 'plan_generation', 'nonwork_purposes'):
        assert response['config'][section] == expected[section]
    assert response['config']['data']['surveys'] == expected['data']['surveys']
    codes = {w['code'] for w in response['warnings']}
    assert {'absolute_path', 'machine_resource', 'historical_default_unresolved',
            'engine_version_unverified', 'data_readiness_unverified'} <= codes
    assert '_config_dir' not in response['config']


@pytest.mark.parametrize('preset_id', ['unknown', 'config_local.json', '..',
                                      '..%2F..%2Fconfig%2Fconfig_local.json'])
def test_unknown_and_unsafe_ids(preset_id):
    status, response = get('/api/config/presets/' + preset_id)
    assert status == 404
    assert response['detail'] == 'Unknown configuration preset'


def test_credentials_are_redacted_in_both_endpoints(tmp_path, monkeypatch):
    preset_id = 'madison-20260928'
    original = main.config_service.load_example(preset_id).config
    config = deepcopy(original)
    config['data']['census_api_key'] = 'SENSITIVE_CENSUS'
    config['gtfs']['api_keys'] = {'example.org': 'SENSITIVE_GTFS'}
    config['extension'] = {'password': 'SENSITIVE_PASSWORD',
                           'nested': [{'access_token': 'SENSITIVE_TOKEN'}],
                           'url': 'https://alice:SENSITIVE_USERPASS@example.org/feed?api_key=SENSITIVE_QUERY&year=2024'}
    config['data']['data_dir'] = str(tmp_path / 'missing')
    # Provision all registry fixtures so list exercises the same public boundary.
    for registered in PRESETS:
        folder = tmp_path / 'examples' / registered
        folder.mkdir(parents=True)
        (folder / 'config_used.json').write_text(json.dumps(config))
    monkeypatch.setattr(main, 'config_service', ConfigService(tmp_path))
    for path in ('/api/config/presets', '/api/config/presets/' + preset_id):
        status, response = get(path)
        assert status == 200
        assert 'SENSITIVE_' not in json.dumps(response)
    _, response = get('/api/config/presets/' + preset_id)
    assert response['config']['gtfs']['api_keys']['example.org'] == ''
    assert response['config']['extension']['url'] == 'https://example.org/feed?api_key=&year=2024'
    assert response['config']['freight'] == original['freight']
    assert {'missing_data', 'credentials_redacted'} <= {w['code'] for w in response['warnings']}


def test_broken_registered_source_does_not_expose_local_path(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'config_service', ConfigService(tmp_path))
    status, response = get('/api/config/presets/madison-20260928')
    assert status == 500
    assert str(tmp_path) not in json.dumps(response)
