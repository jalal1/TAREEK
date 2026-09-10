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
def smoke_config_path(repo_root) -> Path:
    """The minimal committed config used by the e2e tier."""
    path = repo_root / "tests" / "fixtures" / "config_smoke.json"
    if not path.exists():
        pytest.fail(f"Smoke config fixture not found: {path}")
    return path


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
            f"Populate it (see notebooks/0.setup_global_data.ipynb) before "
            f"running -m e2e / -m e2e_matsim."
        )
    return db_path


@pytest.fixture(scope="session")
def require_java(repo_root):
    """Return the MATSim jar path, FAILING if Java or the jar is missing."""
    jar = repo_root / "matsim" / "matsim_25" / "matsim_25.jar"
    if not jar.exists():
        pytest.fail(f"e2e_matsim requires the MATSim jar at {jar}, not found.")
    if shutil.which("java") is None:
        pytest.fail(
            "e2e_matsim requires a Java runtime on PATH ('java' not found). "
            "Install a JDK (21 recommended) before running -m e2e_matsim."
        )
    return jar
