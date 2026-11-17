"""Lossless configuration loading, editing and compatibility diagnostics.

New configurations use config_local.json. Historical inputs deliberately do
not inherit that baseline: missing engine options can have behavioral meaning.
This module has no simulation, database, web-framework or filesystem-write side
effects. Diagnostics are separate from the exported engine configuration.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
from pathlib import Path, PureWindowsPath
import shutil


class ConfigurationError(ValueError):
    """Invalid source or configuration structure."""


@dataclass
class ConfigResult:
    config: dict
    issues: list = field(default_factory=list)
    migrations: list = field(default_factory=list)


def deep_merge(base, overrides):
    """Copy mappings recursively; lists, scalars and null replace whole values."""
    result = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def user_config(config):
    """Remove known execution state, retaining annotations and unknown options."""
    result = deepcopy(config)
    for key in ('_config_dir', '_demand_budget'):
        result.pop(key, None)
    matsim = result.get('matsim')
    if isinstance(matsim, dict):
        for key in ('_survey_typical_durations', '_survey_activity_params'):
            matsim.pop(key, None)
    # The runner always derives this from county centroids.
    if (isinstance(result.get('coordinates'), dict)
            and (result.get('region', {}).get('counties') or result.get('network', {}).get('counties'))):
        result['coordinates'].pop('utm_epsg', None)
    return result


def _leaves(value, path=''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, f'{path}.{key}' if path else key)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _leaves(child, f'{path}[{i}]')
    else:
        yield path, value


def portability_issues(config):
    """Report machine bindings without rewriting paths or querying the host."""
    issues = []
    for path, value in _leaves(config):
        if any(part.startswith('_') for part in path.split('.')):
            continue
        name = path.rsplit('.', 1)[-1]
        if isinstance(value, str) and value and (
            name.endswith(('_dir', '_file')) or name == 'file'
        ):
            absolute = Path(value).is_absolute() or PureWindowsPath(value).is_absolute()
            issues.append({'code': 'absolute_path' if absolute else 'relative_path',
                           'path': path, 'message': (
                               'Machine-specific absolute path; verify on the execution host.'
                               if absolute else
                               'Relative path; verify against the engine resolver and exported config location.')})
        if name in ('heap_size_gb', 'network_heap_size_gb', 'heap_ram_fraction',
                    'num_processes', 'numOfThreads') or path.endswith('numberOfThreads'):
            issues.append({'code': 'machine_resource', 'path': path,
                           'message': f'Execution-host resource setting: {value}; review available RAM/CPUs.'})
    return issues


def validate_structure(config):
    """Validate the service contract without checking files or installed tools.

    Unknown keys are allowed, including engine extensions. This is not a
    replacement for the engine's detailed semantic and MATSim XML validation.
    """
    if not isinstance(config, dict):
        raise ConfigurationError('Configuration must be a JSON object')
    for section in ('data', 'plan_generation', 'network', 'matsim'):
        if not isinstance(config.get(section), dict):
            raise ConfigurationError(f'{section} must be an object')
    for section in ('region', 'coordinates', 'freight', 'counts', 'modes',
                    'time_models', 'od_matrix', 'duration_constraints'):
        if section in config and not isinstance(config[section], dict):
            raise ConfigurationError(f'{section} must be an object')
    counties = config.get('region', {}).get('counties', config['network'].get('counties'))
    if counties is not None and (not isinstance(counties, list) or not counties or
            any(not isinstance(c, str) or len(c) != 5 or not c.isdigit() for c in counties)):
        raise ConfigurationError('counties must be a nonempty array of five-digit GEOID strings')
    if counties is None and not config['network'].get('polygon'):
        raise ConfigurationError('A county selection or network polygon is required')
    if not isinstance(config['data'].get('data_dir'), str) or not config['data']['data_dir']:
        raise ConfigurationError('data.data_dir must be a nonempty string')
    surveys = config['data'].get('surveys', [])
    if not isinstance(surveys, list) or any(not isinstance(s, dict) for s in surveys):
        raise ConfigurationError('data.surveys must be an array of objects')
    for survey in surveys:
        if 'roles' in survey and not isinstance(survey['roles'], dict):
            raise ConfigurationError('survey.roles must be an object')
    if not isinstance(config['matsim'].get('configurable_params', {}), dict):
        raise ConfigurationError('matsim.configurable_params must be an object')
    for section, keys in {
        'matsim': ('run_simulation', 'transit_network', 'scale_transit_pce', 'write_intermediate_output'),
        'network': ('clean_network', 'rebuild_network'),
        'freight': ('enabled',),
    }.items():
        for key in keys:
            if key in config.get(section, {}) and not isinstance(config[section][key], bool):
                raise ConfigurationError(f'{section}.{key} must be a boolean')
    for section, key in (('plan_generation', 'scaling_factor'),
                         ('plan_generation', 'num_processes'),
                         ('matsim', 'heap_size_gb')):
        if key in config[section]:
            value = config[section][key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ConfigurationError(f'{section}.{key} must be a positive number')
    params = config['matsim'].get('configurable_params', {})
    if config['matsim'].get('mode') not in ('basic', 'uber'):
        raise ConfigurationError('matsim.mode must be basic or uber')
    if 'lastIteration' in params:
        try:
            value = params['lastIteration']
            valid = not isinstance(value, bool) and int(value) >= 0 and float(value) == int(value)
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            raise ConfigurationError('matsim.configurable_params.lastIteration must be a non-negative integer')
    for key in ('qsim.flowCapacityFactor', 'qsim.storageCapacityFactor'):
        if key in params:
            value = params[key]
            try:
                valid = not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise ConfigurationError(f'matsim.configurable_params.{key} must be a positive number')
    for path, value in _leaves(config):
        if isinstance(value, float) and not math.isfinite(value):
            raise ConfigurationError(f'{path} must be finite')


class ConfigService:
    def __init__(self, project_root=None):
        self.root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]

    @staticmethod
    def _read(path):
        try:
            config = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f'Cannot load configuration {path}: {exc}') from exc
        if not isinstance(config, dict):
            raise ConfigurationError('Configuration must be a JSON object')
        return config

    def list_examples(self):
        return sorted(p.parent.name for p in (self.root / 'examples').glob('*/config_used.json'))

    def load_baseline(self):
        return self.prepare(self._read(self.root / 'config' / 'config_local.json'))

    def load_example(self, example_id):
        if not isinstance(example_id, str) or example_id not in self.list_examples():
            raise ConfigurationError(f'Unknown example: {example_id!r}')
        path = self.root / 'examples' / example_id / 'config_used.json'
        if not path.resolve().is_relative_to((self.root / 'examples').resolve()):
            raise ConfigurationError('Example path must remain inside examples')
        return self.prepare(self._read(path), historical=True)

    def prepare(self, config, overrides=None, historical=False):
        if not isinstance(config, dict) or (overrides is not None and not isinstance(overrides, dict)):
            raise ConfigurationError('Configuration and overrides must be objects')
        merged = deep_merge(config, overrides or {})
        validate_structure(merged)
        result = ConfigResult(user_config(merged))
        # Compatibility migration 1: old county location. Keep the original
        # field too; region.counties is the current engine's preferred source.
        network = result.config['network']
        if 'counties' not in result.config.get('region', {}) and network.get('counties'):
            result.config.setdefault('region', {})['counties'] = deepcopy(network['counties'])
            result.migrations.append('legacy_network_counties_to_region')
        # Compatibility migration 2: null is exactly the engine's missing-value
        # behavior. Do not merge the rest of today's baseline into old inputs.
        if historical and 'roundabout_capacity_per_lane' not in network:
            network['roundabout_capacity_per_lane'] = None
            result.migrations.append('explicit_no_roundabout_capacity_override')
        if historical:
            for path, key, section, behavior in (
                ('matsim.scale_transit_pce', 'scale_transit_pce', 'matsim', 'true'),
                ('time_models.departure_bandwidth_minutes', 'departure_bandwidth_minutes', 'time_models', '10 minutes'),
            ):
                if key not in result.config.get(section, {}):
                    result.issues.append({'code': 'historical_default_unresolved', 'path': path,
                        'message': f'Absent in historical input; current engine defaults to {behavior}. '
                                   'Verify original engine behavior before reproduction; no value was inferred.'})
        result.issues.extend(portability_issues(result.config))
        return result

    def assemble(self, form_data):
        """Accept the existing wizard payload or a full config editing envelope.

        {"example_id": name, "overrides": {...}} edits an example.
        {"config": {...}, "overrides": {...}} edits an imported historical input.
        Flat engine sections and legacy counties/surveys edit the baseline.
        """
        if not isinstance(form_data, dict):
            raise ConfigurationError('Request body must be an object')
        payload = deepcopy(form_data)
        for section in ('region', 'data'):
            if section in payload and not isinstance(payload[section], dict):
                raise ConfigurationError(f'{section} must be an object')
        example = payload.pop('example_id', None)
        imported = payload.pop('config', None)
        overrides = payload.pop('overrides', {})
        if not isinstance(overrides, dict):
            raise ConfigurationError('overrides must be an object')
        if example is not None and imported is not None:
            raise ConfigurationError('Choose example_id or config, not both')
        base = (self.load_example(example).config if example is not None else
                imported if imported is not None else self.load_baseline().config)
        if 'counties' in payload:
            payload.setdefault('region', {})['counties'] = payload.pop('counties')
        if 'surveys' in payload:
            payload.setdefault('data', {})['surveys'] = payload.pop('surveys')
        return self.prepare(base, deep_merge(payload, overrides),
                            historical=example is not None or imported is not None)

    def export_submission(self, payload):
        """Export complete inputs without consulting or merging any baseline.

        Existing source/edit envelopes remain supported. Only the legacy wizard
        shape (top-level counties/surveys) opts into baseline assembly, with an
        explicit diagnostic so a malformed full config never falls back to it.
        """
        if not isinstance(payload, dict):
            raise ConfigurationError('Request body must be a complete configuration object')
        # A full engine config is authoritative, including unknown top-level keys.
        if 'data' in payload or 'region' in payload:
            if not ('counties' in payload or 'surveys' in payload):
                return self.prepare(payload, historical=True)
        if 'config' in payload or 'example_id' in payload:
            if 'config' in payload and not isinstance(payload['config'], dict):
                raise ConfigurationError('config must be a complete configuration object')
            if 'example_id' in payload and not isinstance(payload['example_id'], str):
                raise ConfigurationError('example_id must be a string')
            return self.assemble(payload)
        if 'counties' in payload or 'surveys' in payload:
            result = self.assemble(payload)
            result.issues.append({'code': 'legacy_export_payload', 'path': '',
                'message': 'Deprecated partial wizard payload: assembled against the maintained baseline. '
                           'Submit the complete loaded configuration to preserve preset settings.'})
            return result
        return self.prepare(payload, historical=True)

    def check_execution_readiness(self, config, config_path):
        """Opt-in host checks, separate from loading/export and non-mutating.

        These basic checks supplement (not replace) ConfigValidator.validate()
        and the runner's data, freight and MATSim preflight checks.
        """
        validate_structure(config)
        issues = portability_issues(config)
        data_dir = Path(config['data']['data_dir'])
        if not data_dir.is_absolute():
            data_dir = Path(config_path).parent / data_dir
        if not data_dir.is_dir():
            issues.append({'code': 'missing_data_dir', 'path': 'data.data_dir',
                           'message': f'Data directory does not exist: {data_dir}'})
        if config['matsim'].get('run_simulation', True) and shutil.which('java') is None:
            issues.append({'code': 'missing_tool', 'path': 'matsim.run_simulation',
                           'message': 'Java is not available on PATH.'})
        return issues
