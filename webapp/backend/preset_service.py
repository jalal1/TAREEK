# SPDX-License-Identifier: GPL-3.0-or-later
"""Example presets found in examples/, and credential-safe public representations."""

from copy import deepcopy
import logging
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    from .config_service import ConfigurationError, portability_issues
except ImportError:
    from config_service import ConfigurationError, portability_issues

logger = logging.getLogger(__name__)

# The engine resolves data_dir relative to the folder of config.json. The main
# README says to save config.json in config/, so ../data is the repo's data/.
DEFAULT_LOCAL_DATA_DIR = '../data'


# Survey types shown with a readable name in the map popup.
SURVEY_LABELS = {'nhts': 'NHTS', 'tbi': 'TBI', 'bham_local': 'Local survey'}


def preset_ids(root):
    """Example folders that can be offered as presets, found automatically.

    An example is a preset when it holds both the engine input
    (config_used.json, whose parameters are applied) and the MATSim
    config.xml of a completed run. IDs are directory names found by this
    scan, never client-supplied paths.
    """
    examples = Path(root) / 'examples'
    return sorted(p.parent.name for p in examples.glob('*/config_used.json')
                  if (p.parent / 'config.xml').is_file())


def _readme_title(folder):
    """First '# ' heading of the example README, or None."""
    try:
        for line in (folder / 'README.md').read_text(encoding='utf-8').splitlines():
            if line.startswith('# '):
                return line[2:].strip()
    except OSError:
        pass
    return None


def _readme_summary(folder, limit=240):
    """First paragraph after the README title, shortened for display."""
    try:
        lines = (folder / 'README.md').read_text(encoding='utf-8').splitlines()
    except OSError:
        return ''
    paragraph, started = [], False
    for line in lines:
        if line.startswith('# '):
            started = True
            continue
        if not started:
            continue
        if line.strip():
            if line.startswith(('#', '|', '```')):
                break
            paragraph.append(line.strip().lstrip('> ').replace('**', '').replace('`', ''))
        elif paragraph:
            break
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', ' '.join(paragraph))  # drop link targets
    return text if len(text) <= limit else text[:limit - 1].rsplit(' ', 1)[0] + '…'


def example_metadata(root, preset_id, config):
    """Region, display name and date derived from the example itself."""
    folder = Path(root) / 'examples' / preset_id
    title = _readme_title(folder)
    # "Chicago, IL experiment — 2026-10-03" and "Twin Cities, MN-WI — TBI ..." -> region.
    region = re.split(r' experiment\b| — ', title, maxsplit=1)[0].strip() if title else ''
    if not region:
        region = preset_id.split('-', 1)[0].title()
    match = re.search(r'(\d{4})(\d{2})(\d{2})$', preset_id)
    date = f'{match[1]}-{match[2]}-{match[3]}' if match else None
    surveys = [s for s in config['data'].get('surveys', []) if isinstance(s, dict)]
    main = next((s for s in surveys if (s.get('weight') or 0) > 0), surveys[0] if surveys else {})
    survey = SURVEY_LABELS.get(main.get('type'), str(main.get('type') or 'survey'))
    name = f'{survey} ({date})' if date else survey
    return {'region': region, 'display_name': name, 'date': date,
            'description': _readme_summary(folder) or title or preset_id}


def _credential_key(key):
    compact = re.sub(r'[^a-z0-9]', '', key.lower())
    return any(word in compact for word in (
        'apikey', 'password', 'passwd', 'secret', 'token', 'credential',
        'authorization', 'privatekey', 'accesskey',
    )) or compact in ('username', 'clientid', 'cookie')


def _annotation_key(key):
    """Help/comment annotations such as _census_api_key_help are not secrets."""
    return key.startswith('_') and key.endswith(('_help', '_comment')) or key in ('_help', '_comment')


# Template placeholders such as YOUR_CENSUS_API_KEY_HERE tell the user what to fill in.
_PLACEHOLDER = re.compile(r'^YOUR_[A-Z0-9_]+$')


def public_config(config):
    """Keep engine fields; blank credential values, including authenticated URLs.

    Credential containers retain their shape (e.g. domain-keyed GTFS API keys).
    Never include removed values in warnings or metadata.
    """
    redacted = []

    def clean(value, path='', sensitive=False):
        if isinstance(value, dict):
            return {key: clean(child, f'{path}.{key}' if path else key,
                               not _annotation_key(key) and (sensitive or _credential_key(key)))
                    for key, child in value.items()}
        if isinstance(value, list):
            return [clean(child, f'{path}[{i}]', sensitive) for i, child in enumerate(value)]
        if sensitive and isinstance(value, str) and _PLACEHOLDER.match(value):
            return value
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
    def __init__(self, config_service, locate=None):
        """locate(counties) -> (lat, lng) or None places the map pin.

        Without a locator (or when it cannot place the counties) the preset
        has location None and the map shows no pin for it.
        """
        self.config_service = config_service
        self.locate = locate

    def load(self, preset_id):
        if not isinstance(preset_id, str) or preset_id not in preset_ids(self.config_service.root):
            raise KeyError(preset_id)
        result = self.config_service.load_example(preset_id)
        config, redacted = public_config(result.config)
        counties = config.get('region', {}).get('counties') or []
        location = self.locate(counties) if self.locate and counties else None
        info = example_metadata(self.config_service.root, preset_id, config)
        metadata = {
            'id': preset_id, 'display_name': info['display_name'],
            'region': info['region'], 'date': info['date'],
            'description': info['description'],
            'location': {'lat': location[0], 'lng': location[1]} if location is not None else None,
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
        # The example's data folder is a path on the computer where it was run
        # (for example /media/volume/... on the server). Use the local data
        # folder of this repository instead, and tell the user.
        original_dir = config['data']['data_dir']
        local_dir = self.local_data_dir()
        data_dir_replaced = None
        if original_dir != local_dir:
            config['data']['data_dir'] = local_dir
            data_dir_replaced = {'from': original_dir, 'to': local_dir}
        # Recompute after the replacement: the old data_dir is no longer an issue.
        warnings = portability_issues(config)
        if redacted:
            warnings.append({'code': 'credentials_redacted', 'path': '',
                             'message': 'API keys or passwords in this example were removed. '
                                        'Add your own in config.json before you run it.'})
        return {**metadata, 'config': config, 'warnings': warnings,
                'migrations': result.migrations, 'data_dir_replaced': data_dir_replaced}

    def local_data_dir(self):
        """data.data_dir of config/config_local.json (the repository's data folder)."""
        try:
            return self.config_service.load_baseline().config['data']['data_dir']
        except ConfigurationError:
            return DEFAULT_LOCAL_DATA_DIR

    def list(self):
        """List loadable presets; one broken example must not hide all others."""
        presets = []
        for preset_id in preset_ids(self.config_service.root):
            try:
                loaded = self.load(preset_id)
            except ConfigurationError as exc:
                logger.warning('Skipping preset %s: %s', preset_id, type(exc).__name__)
                continue
            presets.append({k: v for k, v in loaded.items() if k != 'config'})
        return presets
