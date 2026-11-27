# SPDX-License-Identifier: GPL-3.0-or-later
"""Download a MATSim release into matsim/<version>/.

Usage:
    python scripts/install_matsim.py              # the default version
    python scripts/install_matsim.py matsim_2026
    python scripts/install_matsim.py matsim_2026 --zip path/to/matsim-2026.0-release.zip

The script downloads the official release zip from GitHub (or uses --zip),
checks its SHA-256, and extracts only the MATSim jar, the library jars and
the licence files:

    matsim/matsim_2026/matsim-2026.0.jar
    matsim/matsim_2026/matsim_2026_lib/*.jar
    matsim/matsim_2026/LICENSE, COPYING

The folder is not tracked by git (.gitignore). matsim_25 is part of the
repository and needs no download. The version table is matsim/versions.py.
"""

import argparse
import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from matsim import versions  # noqa: E402


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _copy_member(zf: zipfile.ZipFile, member: str, target: Path) -> None:
    """Write one zip member to a fixed target path (no path from the zip)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member) as src, open(target, 'wb') as dst:
        shutil.copyfileobj(src, dst)


def install(version: str, zip_path: Path = None, force: bool = False) -> Path:
    spec = versions.MATSIM_VERSIONS.get(version, {}).get('download')
    if spec is None:
        raise SystemExit(f"No download is defined for '{version}'. "
                         f"Versions with a download: "
                         f"{[v for v, s in versions.MATSIM_VERSIONS.items() if s.get('download')]}")

    dest = versions.version_dir(version)
    jar_name = Path(spec['jar']).name
    if (dest / jar_name).exists() and not force:
        print(f"{dest / jar_name} exists. Use --force to install again.")
        return dest

    with tempfile.TemporaryDirectory() as tmp:
        if zip_path is None:
            zip_path = Path(tmp) / Path(spec['url']).name
            print(f"Download {spec['url']} ...")
            urllib.request.urlretrieve(spec['url'], zip_path)
        digest = _sha256(zip_path)
        if digest != spec['sha256']:
            raise SystemExit(f"SHA-256 is wrong for {zip_path}:\n  got      {digest}\n"
                             f"  expected {spec['sha256']}")
        print(f"SHA-256 is correct ({digest}).")

        staging = Path(tmp) / 'staging'
        lib_dir = staging / spec['lib_dir']
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            if spec['jar'] not in names:
                raise SystemExit(f"{spec['jar']} is not in the zip.")
            _copy_member(zf, spec['jar'], staging / jar_name)
            n_libs = 0
            for name in names:
                if (name.startswith(spec['libs']) and name.endswith('.jar')
                        and '/' not in name[len(spec['libs']):]):
                    _copy_member(zf, name, lib_dir / Path(name).name)
                    n_libs += 1
            for name in spec.get('license_files', []):
                if name in names:
                    _copy_member(zf, name, staging / Path(name).name)

        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(staging, dest)

    print(f"Installed {version}: {dest / jar_name} + {n_libs} library jars in "
          f"{dest / spec['lib_dir']}")
    return dest


def check_java(version: str) -> bool:
    """Print the Java that TAREEK will use for ``version``, or what is missing."""
    try:
        java = versions.resolve_java({'version': version}, version)
        versions.check_java_for_version(java, version)
    except RuntimeError as exc:
        print()
        print("Java check: NOT OK.")
        print(exc)
        return False
    print()
    print(f"Java check: OK ({java}, Java {versions.java_release(java)}).")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('version', nargs='?', default=versions.DEFAULT_VERSION,
                        help=f"default: {versions.DEFAULT_VERSION}")
    parser.add_argument('--zip', type=Path, help="use this release zip, do not download")
    parser.add_argument('--force', action='store_true', help="install again")
    args = parser.parse_args()
    install(args.version, args.zip, args.force)
    if not check_java(args.version):
        sys.exit(1)


if __name__ == '__main__':
    main()
