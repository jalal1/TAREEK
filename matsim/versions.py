# SPDX-License-Identifier: GPL-3.0-or-later
"""MATSim versions: the jar folder and the Java binary for each version.

The config key ``matsim.version`` selects the folder ``matsim/<version>/``.
The same key also selects the Java binary, because the versions need
different Java releases:

    matsim_2026  MATSim 2026.0, jar + matsim_2026_lib/, Java 25 or newer (default)
    matsim_25    MATSim 2025.0, one shaded jar, Java 21 or newer

matsim_2026 is the default since 2026-11-26 (A/B on Madison: same count fit
and mode shares as matsim_25 within 0.1 percentage point; fixes the
LegHistogram bug of 2025.0). Install it with
``python scripts/install_matsim.py matsim_2026``.

To go back to MATSim 2025.0, set ``matsim.version`` to ``"matsim_25"``.
Do not change other keys.

Java search order (first match wins; each candidate must be at least the
Java release that the version needs):

1. ``matsim.java_executable`` in the config (path to the java binary or to a
   Java home folder). This key applies to all versions.
2. Environment variable ``TAREEK_JAVA_<release>``, for example
   ``TAREEK_JAVA_25=/home/me/jdk/jdk25/bin/java``.
3. ``java`` on PATH.
4. ``$JAVA_HOME`` and the Java folders of the operating system
   (``/usr/lib/jvm/*`` on Linux, ``C:\\Program Files\\<vendor>\\*`` on Windows).

If no candidate is applicable, ``resolve_java`` raises an error that tells
the operator what to set.

Main entry: matsim_25 starts ``org.matsim.core.controler.Controler``.
matsim_2026 starts ``matsim/launcher/TareekController.java`` (Java runs the
source file directly). MATSim 2026.0 has a new scale-factor check that wants
countsScaleFactor == flowCapacityFactor (a MATSim bug, fixed after the
release by PR #5016) and storageCapacityFactor == flowCapacityFactor; its
tolerance cannot be set in config.xml (PR #4706, after the release). The
launcher does the corrected check and then starts the normal Controler.

Network preparation (the OSM converter ``RunSimpleNetworkReaderJalal`` and
``NetworkCleaner``) always uses NETWORK_TOOLS_VERSION. The converter is a
custom class that is only in matsim_25.jar, and network.xml has the same
format in both versions.

Config differences (checked 2026-11-26 with ``org.matsim.run.CreateFullConfig``
on both jars; not guessed):
- No core parameter of 2025.0 is removed in 2026.0.
- Only in 2026.0: module ``dsim``, ``qsim.delayInstantTeleportationArrivals``,
  ``routing`` teleportedModeParameters ``personSpeedAttribute``.
- Changed defaults: ``controller.compressionType`` gzip -> zst,
  ``routing.accessEgressType`` none -> accessEgressModeToLink,
  ``scoring.writeExperiencedPlans`` false -> true. The template
  ``matsim/configs/basic/config.xml`` sets the 2025.0 values for all three,
  so both versions run the same model and write ``.gz`` outputs.
"""

import functools
import logging
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

MATSIM_DIR = Path(__file__).parent

DEFAULT_VERSION = 'matsim_2026'
NETWORK_TOOLS_VERSION = 'matsim_25'

MATSIM_VERSIONS: Dict[str, Dict] = {
    'matsim_25': {
        'release': '2025.0',
        'java_release': 21,
        'main': 'org.matsim.core.controler.Controler',
        'install_hint': 'matsim_25.jar is part of the repository.',
    },
    'matsim_2026': {
        'release': '2026.0',
        'java_release': 25,
        # Source file, run by Java source-file mode (needs module jdk.compiler).
        # Replaces a 2026.0 scale-factor check that stops every Tareek run;
        # see the comment in the file.
        'main_source': 'launcher/TareekController.java',
        'install_hint': 'Run: python scripts/install_matsim.py matsim_2026',
        'download': {
            'url': 'https://github.com/matsim-org/matsim-libs/releases/download/'
                   '2026.0/matsim-2026.0-release.zip',
            'sha256': '210ce7d7f39751053229f65299d2288ac137ae7abf6f4e5dd4548ef4888063c6',
            'jar': 'matsim-2026.0/matsim-2026.0.jar',
            'libs': 'matsim-2026.0/libs/',
            'license_files': ['matsim-2026.0/LICENSE', 'matsim-2026.0/COPYING'],
            'lib_dir': 'matsim_2026_lib',
        },
    },
}

# Parameters that exist in only some versions. MATSim stops on an unknown
# parameter, so config_manager removes these for the other versions.
# Key: "module.param" or "module" (the full module).
VERSION_ONLY_PARAMS: Dict[str, Iterable[str]] = {
    'dsim': ('matsim_2026',),
    'qsim.delayInstantTeleportationArrivals': ('matsim_2026',),
}


# Defaults that changed in 2026.0. config_manager writes the 2025.0 value for
# every version (all three parameters exist in both), unless the config
# already sets the parameter. Result: same model and ".gz" output files.
PINNED_DEFAULTS = (
    ('controller', 'compressionType', 'gzip'),
    ('routing', 'accessEgressType', 'none'),
    ('scoring', 'writeExperiencedPlans', 'false'),
)

# Defaults that Tareek writes for one version when the mobsim is hermes,
# unless the config already sets the parameter.
# oneThreadPerHandler: 2026.0 fixed the LegHistogram race (PR #3936). A/B on
# 2026-11-26: Madison 53.6 -> 39.3 s/it, Birmingham 145.4 -> 104.1 s/it, the
# same results. Not for matsim_25 (crash in LegHistogram).
HERMES_VERSION_DEFAULTS = {
    'matsim_2026': (('eventsManager', 'oneThreadPerHandler', 'true'),),
}


def param_allowed(version: str, module: str, param: Optional[str] = None) -> bool:
    """False when ``module[.param]`` exists only in other versions."""
    for key in ((module,) if param is None else (module, f'{module}.{param}')):
        only = VERSION_ONLY_PARAMS.get(key)
        if only is not None and version not in only:
            return False
    return True


def get_version(matsim_config: Optional[Dict]) -> str:
    """Return ``matsim.version`` (default DEFAULT_VERSION, ``matsim_2026``)."""
    return (matsim_config or {}).get('version', DEFAULT_VERSION)


def version_dir(version: str) -> Path:
    return MATSIM_DIR / version


def get_jar_path(version: str) -> Path:
    """Return the MATSim jar of ``version``; clear error if it is missing."""
    base = version_dir(version)
    jars = sorted(base.glob('*.jar'))
    if not jars:
        hint = MATSIM_VERSIONS.get(version, {}).get('install_hint', '')
        raise FileNotFoundError(f"No MATSim jar found in {base}. {hint}".strip())
    return jars[0]


def get_lib_path(version: str) -> Optional[Path]:
    """Return the ``*_lib`` folder of ``version``, or None (shaded jar)."""
    libs = sorted(p for p in version_dir(version).glob('*_lib') if p.is_dir())
    return libs[0] if libs else None


def build_classpath(version: str, os_type: Optional[str] = None) -> str:
    """Jar plus ``<lib>/*`` when the version has a lib folder."""
    os_type = os_type or platform.system()
    sep = ';' if os_type == 'Windows' else ':'
    jar = get_jar_path(version)
    lib = get_lib_path(version)
    if lib is not None:
        return f"{jar}{sep}{os.path.join(str(lib), '*')}"
    return str(jar)


def main_args(version: str) -> List[str]:
    """Arguments after the classpath that start MATSim for ``version``."""
    spec = MATSIM_VERSIONS.get(version, {})
    if spec.get('main_source'):
        return [str(MATSIM_DIR / spec['main_source'])]
    return [spec.get('main', 'org.matsim.core.controler.Controler')]


# ── Java ────────────────────────────────────────────────────────────────

_VERSION_RE = re.compile(r'version "(\d+)(?:\.(\d+))?')


def parse_java_release(version_output: str) -> Optional[int]:
    """Return the Java feature release from ``java -version`` output.

    ``openjdk version "25.0.5.1"`` -> 25, ``java version "1.8.0_241"`` -> 8.
    """
    m = _VERSION_RE.search(version_output or '')
    if not m:
        return None
    first = int(m.group(1))
    if first == 1 and m.group(2):
        return int(m.group(2))
    return first


@functools.lru_cache(maxsize=None)
def java_release(java: str) -> Optional[int]:
    """Run ``<java> -version`` and return the release, or None if it fails."""
    try:
        result = subprocess.run([java, '-version'], capture_output=True,
                                text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_java_release(result.stderr + result.stdout)


@functools.lru_cache(maxsize=None)
def java_has_compiler(java: str) -> bool:
    """True when ``java`` can run a .java source file (module jdk.compiler)."""
    try:
        result = subprocess.run([java, '--list-modules'], capture_output=True,
                                text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.startswith('jdk.compiler@') or line == 'jdk.compiler'
               for line in result.stdout.split())


def check_java_for_version(java: str, version: str) -> None:
    """Raise RuntimeError when ``java`` cannot start ``version``."""
    if MATSIM_VERSIONS.get(version, {}).get('main_source') and not java_has_compiler(java):
        raise RuntimeError(
            f"{java} has no module jdk.compiler, so it cannot run "
            f"{MATSIM_VERSIONS[version]['main_source']} for matsim.version '{version}'. "
            f"Use a full JDK or a runtime with jdk.compiler (for example Ubuntu "
            f"openjdk-25-jre-headless).")


def _java_in(home: Path) -> Path:
    exe = 'java.exe' if platform.system() == 'Windows' else 'java'
    return home / 'bin' / exe


def _normalise(candidate: str) -> str:
    """Accept a java binary or a Java home folder."""
    p = Path(candidate).expanduser()
    if p.is_dir():
        return str(_java_in(p))
    return str(p) if candidate.startswith('~') else candidate


def _system_java_candidates() -> List[str]:
    """Java binaries in JAVA_HOME and the usual operating-system folders."""
    homes: List[Path] = []
    if os.environ.get('JAVA_HOME'):
        homes.append(Path(os.environ['JAVA_HOME']))
    roots = [Path('/usr/lib/jvm'), Path('/opt/java'), Path('/usr/java')]
    if platform.system() == 'Windows':
        for var in ('ProgramFiles', 'ProgramW6432'):
            base = os.environ.get(var)
            if base:
                for vendor in ('Java', 'Eclipse Adoptium', 'Microsoft',
                               'Amazon Corretto', 'Zulu', 'BellSoft'):
                    roots.append(Path(base) / vendor)
    for root in roots:
        try:
            homes.extend(sorted(d for d in root.iterdir() if d.is_dir()))
        except OSError:
            continue
    out: List[str] = []
    for home in homes:
        java = _java_in(home)
        if java.exists() and str(java) not in out:
            out.append(str(java))
    return out


def resolve_java(matsim_config: Optional[Dict] = None,
                 version: Optional[str] = None) -> str:
    """Return the Java binary for ``version`` (see the module docstring).

    Raises RuntimeError when the version needs a Java release that cannot be
    found. A version that is not in MATSIM_VERSIONS uses ``java`` on PATH
    without a check.
    """
    matsim_config = matsim_config or {}
    version = version or get_version(matsim_config)
    need = MATSIM_VERSIONS.get(version, {}).get('java_release')

    explicit = matsim_config.get('java_executable')
    env_name = f'TAREEK_JAVA_{need}' if need else None
    env_value = os.environ.get(env_name) if env_name else None

    if need is None:
        return _normalise(explicit) if explicit else 'java'

    tried: List[str] = []

    # 1 + 2: explicit settings must be correct; do not fall through silently.
    for source, value in (('matsim.java_executable', explicit), (env_name, env_value)):
        if not value:
            continue
        java = _normalise(value)
        rel = java_release(java)
        if rel is not None and rel >= need:
            logger.info(f"Java for {version}: {java} (Java {rel}, from {source})")
            return java
        raise RuntimeError(
            f"{source} = {value} is {'not a working java binary' if rel is None else f'Java {rel}'}, "
            f"but matsim.version '{version}' (MATSim "
            f"{MATSIM_VERSIONS[version]['release']}) needs Java {need} or newer."
        )

    # 3: java on PATH.
    on_path = shutil.which('java')
    candidates = ([on_path] if on_path else []) + _system_java_candidates()
    best: Optional[tuple] = None
    for java in candidates:
        rel = java_release(java)
        tried.append(f"{java} (Java {rel if rel is not None else '?'})")
        if rel is None or rel < need:
            continue
        if java == on_path:
            best = (rel, java)
            break
        # 4: prefer the exact release, then the lowest release above it.
        if best is None or (rel - need) < (best[0] - need):
            best = (rel, java)
    if best is not None:
        logger.info(f"Java for {version}: {best[1]} (Java {best[0]})")
        return best[1]

    raise RuntimeError(
        f"matsim.version '{version}' (MATSim {MATSIM_VERSIONS[version]['release']}) "
        f"needs Java {need} or newer, but no such Java was found. "
        f"Tried: {', '.join(tried) or 'nothing (no java on PATH)'}. "
        f"Set the environment variable TAREEK_JAVA_{need} or the config key "
        f"matsim.java_executable to a Java {need} binary, or set "
        f"matsim.version to 'matsim_25' (MATSim 2025.0, Java 21)."
    )


def describe(matsim_config: Optional[Dict] = None) -> Dict:
    """Version, release, jar, classpath and Java for logging and tests."""
    version = get_version(matsim_config)
    java = resolve_java(matsim_config, version)
    return {
        'version': version,
        'release': MATSIM_VERSIONS.get(version, {}).get('release'),
        'jar': str(get_jar_path(version)),
        'classpath': build_classpath(version),
        'java': java,
        'java_release': java_release(java),
        'main': main_args(version),
    }
