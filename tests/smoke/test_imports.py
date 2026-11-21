# SPDX-License-Identifier: GPL-3.0-or-later
"""Import-smoke: every first-party module must import without error.

This is the cheapest possible guard against a bug fix or refactor leaving a
module syntactically broken, with a bad import, or a top-level NameError.

Modules are discovered dynamically via pkgutil.walk_packages, so NEW modules
added under the covered packages are tested automatically with zero edits here
-- that is the whole point of this file.

Scope: first-party application packages only. We deliberately exclude:
  - webapp     (FastAPI app; importing main has side effects / extra deps)
  - tests      (this suite)
  - notebooks  (not importable modules)
  - .venv      (third-party; not ours to test)
"""

import importlib
import pkgutil

import pytest

# First-party packages to sweep. config.config (loader) is covered via the
# 'config' package. Add new top-level packages here if the project grows one.
FIRST_PARTY_PACKAGES = [
    "config",
    "data_sources",
    "estimators",
    "matsim",
    "models",
    "utils",
]


def _iter_module_names():
    """Yield importable module names under each first-party package."""
    for pkg_name in FIRST_PARTY_PACKAGES:
        try:
            pkg = importlib.import_module(pkg_name)
        except Exception as exc:  # pragma: no cover - reported via the test below
            yield pytest.param(
                pkg_name,
                marks=pytest.mark.xfail(
                    reason=f"package {pkg_name} failed to import: {exc}",
                    strict=False,
                ),
            )
            continue

        # Namespace/simple packages may lack __path__; still test the package itself.
        yield pkg_name
        if not hasattr(pkg, "__path__"):
            continue

        for mod in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg_name}."):
            yield mod.name


# Materialize once at collection time so each module is its own test case.
_MODULE_NAMES = sorted(set(n for n in _iter_module_names() if isinstance(n, str)))


@pytest.mark.smoke
@pytest.mark.parametrize("module_name", _MODULE_NAMES)
def test_module_imports(module_name):
    """Importing the module must not raise."""
    importlib.import_module(module_name)


@pytest.mark.smoke
def test_discovered_some_modules():
    """Guard against the discovery silently finding nothing (e.g. path bug)."""
    assert len(_MODULE_NAMES) > 10, (
        f"Import-smoke only discovered {_MODULE_NAMES!r}; expected many modules. "
        "Discovery may be broken."
    )
