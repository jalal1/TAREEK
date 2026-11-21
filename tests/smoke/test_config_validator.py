# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke tests for ConfigValidator: the real config passes, bad configs fail."""

import json

import pytest

from utils.config_validator import ConfigValidator, ConfigValidationError


@pytest.mark.smoke
def test_real_local_config_passes(real_config_path):
    """The config the developer actually runs must validate cleanly."""
    config = ConfigValidator(real_config_path).validate()
    # validate() normalizes data_dir to an absolute path; sanity-check structure.
    for section in ConfigValidator.REQUIRED_SECTIONS:
        assert section in config, f"required section {section!r} missing after validate()"


@pytest.mark.smoke
def test_smoke_fixture_config_passes(smoke_config_path):
    """The committed e2e fixture config must itself be valid."""
    config = ConfigValidator(smoke_config_path).validate()
    assert config["region"]["counties"] == ["27003"]


@pytest.mark.smoke
def test_missing_file_raises():
    with pytest.raises(ConfigValidationError):
        ConfigValidator("does/not/exist/config.json")


@pytest.mark.smoke
def test_invalid_json_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json ", encoding="utf-8")
    with pytest.raises(ConfigValidationError):
        ConfigValidator(bad)


@pytest.mark.smoke
def test_missing_required_section_raises(tmp_path, real_config_path):
    """Dropping a required top-level section must be rejected."""
    config = json.loads(real_config_path.read_text(encoding="utf-8"))
    config.pop("matsim", None)  # 'matsim' is in REQUIRED_SECTIONS
    path = tmp_path / "no_matsim.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigValidationError):
        ConfigValidator(path).validate()


@pytest.mark.smoke
def test_empty_counties_list_raises(tmp_path, smoke_config_path):
    """A region with an empty counties list must be rejected."""
    config = json.loads(smoke_config_path.read_text(encoding="utf-8"))
    config["region"]["counties"] = []
    path = tmp_path / "empty_counties.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigValidationError):
        ConfigValidator(path).validate()
