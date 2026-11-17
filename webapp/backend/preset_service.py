"""Curated regional presets and credential-safe public representations."""

from copy import deepcopy
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# IDs are exact example directory names, never client-supplied filesystem paths.
# Coordinates are approximate regional locations (latitude, longitude) for map markers.
PRESETS = {
    'losangeles-20261006': ('Los Angeles — NHTS', 'Los Angeles', 'Los Angeles and Orange counties with NHTS demand.', (34.05, -118.24)),
    'newyork-20261006': ('New York — NHTS', 'New York', 'New York metropolitan experiment spanning New York and New Jersey.', (40.71, -74.01)),
    'madison-20260928': ('Madison — NHTS', 'Madison', 'Dane County experiment with NHTS demand.', (43.07, -89.4)),
    'chicago-20261003': ('Chicago — NHTS', 'Chicago', 'Cook, DuPage and Lake counties with NHTS demand.', (41.88, -87.63)),
    'twincities-20260928': ('Twin Cities — NHTS', 'Twin Cities', 'Minnesota/Wisconsin metropolitan experiment using NHTS.', (44.98, -93.27)),
    'twincities-tbi-20260930': ('Twin Cities — TBI', 'Twin Cities', 'Same metropolitan region using the 2023 Travel Behavior Inventory.', (44.98, -93.27)),
    'birmingham-20260928': ('Birmingham — NHTS', 'Birmingham', 'Jefferson and Shelby counties with NHTS demand.', (33.52, -86.8)),
    'birmingham-localsurvey-20261001': ('Birmingham — local survey', 'Birmingham', 'Local survey for trips, with NHTS person-days for demand estimation.', (33.52, -86.8)),
}


def _credential_key(key):
    compact = re.sub(r'[^a-z0-9]', '', key.lower())
    return any(word in compact for word in (
        'apikey', 'password', 'passwd', 'secret', 'token', 'credential',
        'authorization', 'privatekey', 'accesskey',
    )) or compact in ('username', 'clientid', 'cookie')


def public_config(config):
    """Keep engine fields; blank credential values, including authenticated URLs.

    Credential containers retain their shape (e.g. domain-keyed GTFS API keys).
    Never include removed values in warnings or metadata.
    """
    redacted = []

    def clean(value, path='', sensitive=False):
        if isinstance(value, dict):
            return {key: clean(child, f'{path}.{key}' if path else key,
                               sensitive or _credential_key(key))
                    for key, child in value.items()}
        if isinstance(value, list):
            return [clean(child, f'{path}[{i}]', sensitive) for i, child in enumerate(value)]
        if sensitive:
            if value:
                redacted.append(path)
            return '' if isinstance(value, str) else None
        if isinstance(value, str) and '://' in value:
            try:
                url = urlsplit(value)
                query = parse_qsl(url.query, keep_blank_values=True)
                if '@' in url.netloc or any(_credential_key(k) for k, _ in query):
                    redacted.append(path)
                    return urlunsplit((url.scheme, url.netloc.rsplit('@', 1)[-1], url.path,
                        urlencode([(k, '' if _credential_key(k) else v) for k, v in query]), ''))
            except ValueError:
                redacted.append(path)
                return ''
        return value

    return clean(config), redacted


class PresetService:
    def __init__(self, config_service):
        self.config_service = config_service

    def load(self, preset_id):
        if preset_id not in PRESETS:
            raise KeyError(preset_id)
        result = self.config_service.load_example(preset_id)
        config, redacted = public_config(result.config)
        name, region, description, location = PRESETS[preset_id]
        metadata = {
            'id': preset_id, 'display_name': name, 'region': region,
            'description': description,
            'location': {'lat': location[0], 'lng': location[1]},
            'source_file': f'examples/{preset_id}/config_used.json',
            'characteristics': {
                'counties': deepcopy(config.get('region', {}).get('counties', [])),
                'surveys': [{k: deepcopy(s[k]) for k in ('type', 'year', 'weight', 'roles') if k in s}
                            for s in config['data'].get('surveys', [])],
                'scaling_factor': config['plan_generation'].get('scaling_factor'),
                'random_seed': config['plan_generation'].get('random_seed'),
                'day_type': config['data'].get('day_type'),
                'survey_months': config['data'].get('survey_months'),
                'matsim_version': config['matsim'].get('version'),
                'mobsim': config['matsim'].get('configurable_params', {}).get('controller.mobsim'),
                'freight_enabled': config.get('freight', {}).get('enabled', False),
                'freight_demand_scale': config.get('freight', {}).get('demand_scale'),
            },
        }
        warnings = deepcopy(result.issues)
        warnings.append({'code': 'engine_version_unverified', 'path': 'matsim.version',
                         'message': 'The snapshot does not identify the original TAREEK code/template revision. '
                                    'Matching the MATSim version alone does not guarantee historical results.'})
        # Report only; never rebase an example's paths onto today's baseline.
        data_dir = Path(config['data']['data_dir'])
        if not data_dir.is_absolute():
            data_dir = self.config_service.root / 'examples' / preset_id / data_dir
        if PureWindowsPath(config['data']['data_dir']).is_absolute() or not data_dir.is_dir():
            warnings.append({'code': 'missing_data', 'path': 'data.data_dir',
                             'message': 'The configured data directory is unavailable or belongs to another host. '
                                        'Survey, counts and freight inputs must be provisioned before execution.'})
        warnings.append({'code': 'data_readiness_unverified', 'path': 'data',
                         'message': 'Individual survey, counts, network and freight resources have not been checked. '
                                    'Run execution-readiness validation on the execution host.'})
        if redacted:
            warnings.append({'code': 'credentials_redacted', 'path': '',
                             'message': 'Credential values were removed; supply credentials locally before execution.'})
        return {**metadata, 'config': config, 'warnings': warnings,
                'migrations': result.migrations}

    def list(self):
        return [{k: v for k, v in self.load(preset_id).items() if k != 'config'}
                for preset_id in PRESETS]
