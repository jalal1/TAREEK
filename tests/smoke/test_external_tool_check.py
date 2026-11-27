# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke tests for the preflight external-binary check.

osmium and java are system packages the pipeline shells out to. Before this
check they surfaced only when the pipeline reached them — osmium after a
~280 MB Geofabrik download, java after plan generation — so a missing package
wasted minutes before reporting itself.

TAREEK does not install them (compiled packages, per-platform installs, root
needed on Linux); it fails fast with the right command for the platform.
"""

import json

import pytest

from utils.config_validator import ConfigValidator, ConfigValidationError


def _write_config(tmp_path, **overrides):
    cfg = {
        'data': {'data_dir': str(tmp_path / 'data')},
        'plan_generation': {},
        'network': {'rebuild_network': True},
        'matsim': {'run_simulation': True, 'version': 'matsim_25'},
    }
    for section, values in overrides.items():
        cfg.setdefault(section, {}).update(values)
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    return path


@pytest.mark.smoke
def test_missing_osmium_is_reported_with_install_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'utils.config_validator.shutil.which',
        lambda tool: None if tool == 'osmium' else '/usr/bin/java',
    )
    validator = ConfigValidator(_write_config(tmp_path))

    with pytest.raises(ConfigValidationError) as exc:
        validator._validate_external_tools()

    message = str(exc.value)
    assert 'osmium' in message
    assert 'osm-tools-installation.md' in message
    # The hint must name a real install command, not just the missing tool.
    assert 'conda install' in message


@pytest.mark.smoke
def test_missing_java_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'utils.config_validator.shutil.which',
        lambda tool: None if tool == 'java' else '/usr/bin/osmium',
    )
    validator = ConfigValidator(_write_config(tmp_path))

    with pytest.raises(ConfigValidationError, match='java'):
        validator._validate_external_tools()


@pytest.mark.smoke
def test_passes_when_tools_present(tmp_path, monkeypatch):
    monkeypatch.setattr('utils.config_validator.shutil.which',
                        lambda tool: f'/usr/bin/{tool}')
    ConfigValidator(_write_config(tmp_path))._validate_external_tools()


@pytest.mark.smoke
def test_java_not_required_when_simulation_is_off(tmp_path, monkeypatch):
    """A plans-only run must not demand a JRE."""
    monkeypatch.setattr(
        'utils.config_validator.shutil.which',
        lambda tool: None if tool == 'java' else '/usr/bin/osmium',
    )
    cfg = _write_config(tmp_path, matsim={'run_simulation': False})
    ConfigValidator(cfg)._validate_external_tools()


@pytest.mark.smoke
def test_default_matsim_2026_without_install_names_the_script(tmp_path, monkeypatch):
    """The default version (no "version" key) is matsim_2026; a missing jar fails at start."""
    from matsim import versions
    monkeypatch.setattr('utils.config_validator.shutil.which',
                        lambda tool: f'/usr/bin/{tool}')
    monkeypatch.setattr(versions, 'MATSIM_DIR', tmp_path)
    cfg = _write_config(tmp_path)
    data = json.loads(cfg.read_text())
    del data['matsim']['version']
    cfg.write_text(json.dumps(data))
    with pytest.raises(ConfigValidationError, match='install_matsim.py matsim_2026'):
        ConfigValidator(cfg)._validate_external_tools()
