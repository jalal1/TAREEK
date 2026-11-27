# SPDX-License-Identifier: GPL-3.0-or-later
"""matsim.version selects the jar, the Java binary and the config.xml settings.

No MATSim run: the jar folders are fakes in tmp_path and the Java release is
patched. Going back to MATSim 2025.0 must need only matsim.version.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from matsim import versions
from matsim.config_manager import ConfigManager
from matsim.runner import MATSimRunner

REPO = Path(__file__).resolve().parents[2]


def _smoke_config(version: str) -> dict:
    cfg = json.loads((REPO / 'tests' / 'fixtures' / 'config_smoke.json').read_text(encoding='utf-8'))
    cfg['matsim']['version'] = version
    return cfg


@pytest.fixture
def fake_matsim_dir(tmp_path, monkeypatch):
    """matsim_25: one shaded jar. matsim_2026: jar + matsim_2026_lib/."""
    (tmp_path / 'matsim_25').mkdir()
    (tmp_path / 'matsim_25' / 'matsim_25.jar').write_bytes(b'')
    d26 = tmp_path / 'matsim_2026'
    (d26 / 'matsim_2026_lib').mkdir(parents=True)
    (d26 / 'matsim-2026.0.jar').write_bytes(b'')
    (d26 / 'matsim_2026_lib' / 'guava.jar').write_bytes(b'')
    monkeypatch.setattr(versions, 'MATSIM_DIR', tmp_path)
    return tmp_path


@pytest.fixture
def fake_javas(monkeypatch, tmp_path):
    """PATH java is Java 21; /usr/lib/jvm-like folders hold 21 and 25."""
    releases = {'/path/java': 21, '/jvm/java-21/bin/java': 21, '/jvm/java-25/bin/java': 25}
    monkeypatch.setattr(versions, 'java_release', lambda j: releases.get(str(j)))
    monkeypatch.setattr(versions, 'java_has_compiler', lambda j: True)
    monkeypatch.setattr(versions.shutil, 'which', lambda name: '/path/java')
    monkeypatch.setattr(versions, '_system_java_candidates',
                        lambda: ['/jvm/java-21/bin/java', '/jvm/java-25/bin/java'])
    for var in ('TAREEK_JAVA_21', 'TAREEK_JAVA_25'):
        monkeypatch.delenv(var, raising=False)
    return releases


@pytest.mark.smoke
@pytest.mark.parametrize('text, release', [
    ('openjdk version "25.0.5.1" 2026-11-17', 25),
    ('openjdk version "21.0.13.1" 2026-11-17', 21),
    ('java version "1.8.0_241"', 8),
    ('openjdk version "25" 2025-09-16', 25),
    ('garbage', None),
])
def test_parse_java_release(text, release):
    assert versions.parse_java_release(text) == release


@pytest.mark.smoke
def test_jar_and_classpath_per_version(fake_matsim_dir):
    assert versions.get_jar_path('matsim_25').name == 'matsim_25.jar'
    assert versions.get_lib_path('matsim_25') is None
    assert versions.build_classpath('matsim_25', 'Linux').endswith('matsim_25.jar')

    assert versions.get_jar_path('matsim_2026').name == 'matsim-2026.0.jar'
    cp = versions.build_classpath('matsim_2026', 'Windows')
    jar, lib = cp.split(';')
    assert jar.endswith('matsim-2026.0.jar')
    assert lib.replace('\\', '/').endswith('matsim_2026_lib/*')


@pytest.mark.smoke
def test_missing_2026_jar_names_the_install_script(tmp_path, monkeypatch):
    monkeypatch.setattr(versions, 'MATSIM_DIR', tmp_path)
    with pytest.raises(FileNotFoundError, match='install_matsim.py matsim_2026'):
        versions.get_jar_path('matsim_2026')


@pytest.mark.smoke
def test_java_selection_per_version(fake_javas):
    # matsim_25: the current Java on PATH (21).
    assert versions.resolve_java({'version': 'matsim_25'}) == '/path/java'
    # matsim_2026: PATH java is 21, so the Java 25 folder is found.
    assert versions.resolve_java({'version': 'matsim_2026'}) == '/jvm/java-25/bin/java'


@pytest.mark.smoke
def test_java_25_missing_gives_clear_error(fake_javas, monkeypatch):
    monkeypatch.setattr(versions, '_system_java_candidates', lambda: ['/jvm/java-21/bin/java'])
    with pytest.raises(RuntimeError) as exc:
        versions.resolve_java({'version': 'matsim_2026'})
    msg = str(exc.value)
    assert 'Java 25' in msg and 'TAREEK_JAVA_25' in msg and 'matsim_25' in msg


@pytest.mark.smoke
def test_env_var_and_config_key(fake_javas, monkeypatch):
    fake_javas['/home/me/jdk25/bin/java'] = 25
    monkeypatch.setenv('TAREEK_JAVA_25', '/home/me/jdk25/bin/java')
    assert versions.resolve_java({'version': 'matsim_2026'}) == '/home/me/jdk25/bin/java'
    # The config key comes first; a too-old Java there is an error, not a fallback.
    with pytest.raises(RuntimeError, match='Java 21'):
        versions.resolve_java({'version': 'matsim_2026',
                               'java_executable': '/jvm/java-21/bin/java'})


@pytest.mark.smoke
@pytest.mark.parametrize('version, java', [
    ('matsim_25', '/path/java'),
    ('matsim_2026', '/jvm/java-25/bin/java'),
])
def test_runner_command_uses_version_jar_and_java(fake_matsim_dir, fake_javas, version, java):
    runner = MATSimRunner({'matsim': {'version': version, 'heap_size_gb': 2}})
    cmd = runner.build_command(Path('config.xml'))
    assert cmd[0] == java
    cp = cmd[cmd.index('-cp') + 1]
    assert ('matsim-2026.0.jar' in cp) == (version == 'matsim_2026')
    assert ('matsim_25.jar' in cp) == (version == 'matsim_25')
    main = cmd[cmd.index('-cp') + 2]
    if version == 'matsim_25':
        assert main == 'org.matsim.core.controler.Controler'
    else:
        assert Path(main).name == 'TareekController.java'
        assert (REPO / 'matsim' / 'launcher' / 'TareekController.java').exists()


@pytest.mark.smoke
def test_2026_needs_java_with_compiler(fake_matsim_dir, fake_javas, monkeypatch):
    monkeypatch.setattr(versions, 'java_has_compiler', lambda j: False)
    runner = MATSimRunner({'matsim': {'version': 'matsim_2026', 'heap_size_gb': 2}})
    with pytest.raises(RuntimeError, match='jdk.compiler'):
        runner.build_command(Path('config.xml'))
    # matsim_25 starts a class from the jar and needs no compiler.
    MATSimRunner({'matsim': {'version': 'matsim_25', 'heap_size_gb': 2}}).build_command(Path('config.xml'))


@pytest.mark.smoke
def test_network_tools_stay_on_matsim_25(fake_matsim_dir, fake_javas):
    from matsim.network_generator import NetworkGenerator
    gen = NetworkGenerator.__new__(NetworkGenerator)
    gen.matsim_config = {'version': 'matsim_2026'}
    assert gen.get_matsim_jar_path().name == 'matsim_25.jar'
    assert gen.get_matsim_java() == '/path/java'


def _write_config_xml(tmp_path: Path, version: str, extra_params: dict = None) -> ET.Element:
    cfg = _smoke_config(version)
    cfg['matsim']['configurable_params'].update(extra_params or {})
    exp = tmp_path / version
    exp.mkdir()
    out = ConfigManager(cfg).generate_config(exp / 'config.xml', exp, 'EPSG:26915', mode='basic')
    return ET.parse(out).getroot()


def _value(root: ET.Element, module: str, param: str):
    for m in root.findall('module'):
        if m.get('name') == module:
            for p in m.findall('param'):
                if p.get('name') == param:
                    return p.get('value')
    return None


@pytest.mark.smoke
@pytest.mark.parametrize('version', ['matsim_25', 'matsim_2026'])
def test_config_xml_pins_changed_defaults(tmp_path, version):
    root = _write_config_xml(tmp_path, version)
    # Defaults that changed in 2026.0 are written with the 2025.0 value.
    assert _value(root, 'controller', 'compressionType') == 'gzip'
    assert _value(root, 'routing', 'accessEgressType') == 'none'
    assert _value(root, 'scoring', 'writeExperiencedPlans') == 'false'
    assert _value(root, 'controller', 'mobsim') == 'hermes'


@pytest.mark.smoke
def test_config_xml_version_only_params(tmp_path):
    extra = {'qsim.delayInstantTeleportationArrivals': True}
    r25 = _write_config_xml(tmp_path, 'matsim_25', extra)
    r26 = _write_config_xml(tmp_path, 'matsim_2026', extra)
    assert _value(r25, 'qsim', 'delayInstantTeleportationArrivals') is None
    assert _value(r26, 'qsim', 'delayInstantTeleportationArrivals') == 'true'


@pytest.mark.smoke
def test_one_thread_per_handler_default_only_for_2026(tmp_path):
    r25 = _write_config_xml(tmp_path, 'matsim_25')
    r26 = _write_config_xml(tmp_path, 'matsim_2026')
    assert _value(r25, 'eventsManager', 'oneThreadPerHandler') is None
    assert _value(r26, 'eventsManager', 'oneThreadPerHandler') == 'true'


@pytest.mark.smoke
def test_one_thread_per_handler_config_value_wins(tmp_path):
    r26 = _write_config_xml(tmp_path, 'matsim_2026',
                            {'eventsManager.oneThreadPerHandler': False})
    assert _value(r26, 'eventsManager', 'oneThreadPerHandler') == 'false'


@pytest.mark.smoke
def test_rollback_needs_only_the_version_key(tmp_path):
    """matsim_2026 -> matsim_25 changes nothing else in config.xml, except
    the oneThreadPerHandler default (unsafe in 2025.0)."""
    def without_events_manager(root):
        for m in list(root.findall('module')):
            if m.get('name') == 'eventsManager':
                for p in list(m.findall('param')):
                    if p.get('name') == 'oneThreadPerHandler':
                        m.remove(p)
        return ET.tostring(root)
    a = without_events_manager(_write_config_xml(tmp_path, 'matsim_25'))
    b = without_events_manager(_write_config_xml(tmp_path, 'matsim_2026'))
    assert a == b
