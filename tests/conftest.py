# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared pytest fixtures for the TAREEK test suite.

Fixture tiers:
  - Always-available (no external deps): repo_root, real_config_path,
    smoke_config_path, tmp_experiments_root.
  - Heavy-dep guards: require_db, require_java. Per project decision these
    FAIL LOUDLY (not skip) when their dependency is missing, so an e2e run on
    a misconfigured machine is obvious rather than silently green.

Import path: the project is run from its root (run_experiment.py adds the root
to sys.path at runtime). We replicate that here so `import models`, `import
utils`, etc. resolve when pytest is invoked from anywhere.
"""

import os
import sys
import shutil
import importlib
import sysconfig
from pathlib import Path

# --- Environment guard (must run before pytest's debugging plugin) ----------
# A sibling working directory, E:\projects\code, is a Python package literally
# named "code". The harness puts E:\projects on sys.path, so a bare
# `import code` resolves to that package instead of the stdlib module. pytest's
# debugging plugin later does `import pdb` -> `import code` and crashes with
# INTERNALERROR ("module 'code' has no attribute 'InteractiveConsole'").
#
# By the time this conftest is imported, the wrong `code` may already be bound
# in sys.modules. Fix it definitively: drop any non-stdlib `code`/`pdb`, then
# load the real stdlib `code` from the standard library directory and pin both
# into sys.modules so every later `import code`/`import pdb` is a cache hit.
def _restore_stdlib_code_module() -> None:
    stdlib_dir = sysconfig.get_paths()["stdlib"]
    existing = sys.modules.get("code")
    existing_file = getattr(existing, "__file__", "") or ""
    if existing is not None and existing_file.startswith(stdlib_dir):
        return  # already the real stdlib module

    # Evict the impostor (and pdb, which caches a reference to code).
    sys.modules.pop("code", None)
    sys.modules.pop("pdb", None)

    # Import the stdlib code.py directly by file location, bypassing sys.path.
    import importlib.util
    code_path = Path(stdlib_dir) / "code.py"
    spec = importlib.util.spec_from_file_location("code", code_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["code"] = module


_restore_stdlib_code_module()
import pdb  # noqa: E402,F401  (now resolves code -> stdlib via sys.modules)

import pytest  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# Make first-party packages importable regardless of pytest's CWD.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def real_config_path(repo_root) -> Path:
    """The real local config (config/config_local.json).

    Used by smoke tests to assert the config the developer actually runs with
    still passes validation.
    """
    path = repo_root / "config" / "config_local.json"
    if not path.exists():
        pytest.fail(f"Expected real config not found: {path}")
    return path


@pytest.fixture(scope="session")
def matsim_version() -> str:
    """MATSim version for the e2e tier: env TAREEK_TEST_MATSIM_VERSION.

    Default "matsim_25". Example: TAREEK_TEST_MATSIM_VERSION=matsim_2026
    pytest -m e2e_matsim (needs scripts/install_matsim.py and Java 25).
    """
    return os.environ.get("TAREEK_TEST_MATSIM_VERSION", "matsim_25")


@pytest.fixture(scope="session")
def smoke_config_path(repo_root, matsim_version, tmp_path_factory) -> Path:
    """The minimal committed config used by the e2e tier.

    When matsim_version is not the version in the fixture, a copy with
    matsim.version changed is written to a temporary folder.
    """
    import json
    path = repo_root / "tests" / "fixtures" / "config_smoke.json"
    if not path.exists():
        pytest.fail(f"Smoke config fixture not found: {path}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("matsim", {}).get("version", "matsim_25") == matsim_version:
        return path
    cfg.setdefault("matsim", {})["version"] = matsim_version
    copy = tmp_path_factory.mktemp("smoke_cfg") / "config_smoke.json"
    copy.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return copy


@pytest.fixture
def tmp_experiments_root(tmp_path) -> Path:
    """A throwaway experiments root so tests never touch ./experiments.

    Pass this to ExperimentRunner(experiments_root=...) in e2e tests.
    """
    root = tmp_path / "experiments"
    root.mkdir()
    return root


@pytest.fixture(scope="session")
def require_db(repo_root):
    """Return the DuckDB path, FAILING if it (or the data dir) is absent.

    Per design: e2e tests must fail loudly, not skip, when the DB is missing.
    """
    db_path = repo_root / "data" / "db" / "trafficsim1.2.duckdb"
    if not db_path.exists():
        pytest.fail(
            f"e2e requires the DuckDB at {db_path}, which was not found. "
            f"The repository does not ship it: run any experiment once "
            f"(python run_experiment.py --config config/config_local.json) "
            f"to create and fill it, then run -m e2e / -m e2e_matsim."
        )
    return db_path


@pytest.fixture(scope="session")
def require_java(repo_root, matsim_version):
    """Return the MATSim jar path, FAILING if the jar or its Java is missing.

    The jar and the Java binary come from matsim/versions.py for
    matsim_version (matsim_25: Java 21; matsim_2026: Java 25).
    """
    from matsim import versions
    try:
        jar = versions.get_jar_path(matsim_version)
    except FileNotFoundError as e:
        pytest.fail(f"e2e_matsim requires the MATSim jar: {e}")
    if shutil.which("java") is None and matsim_version == "matsim_25":
        pytest.fail(
            "e2e_matsim requires a Java runtime on PATH ('java' not found). "
            "Install a JDK (21 recommended) before running -m e2e_matsim."
        )
    try:
        versions.resolve_java({"version": matsim_version}, matsim_version)
    except RuntimeError as e:
        pytest.fail(f"e2e_matsim: {e}")
    return jar
