# SPDX-License-Identifier: GPL-3.0-or-later
"""
MATSim simulation runner
Handles execution of MATSim simulations with cross-platform support
"""

import subprocess
import platform
import os
from pathlib import Path
from typing import Dict, Optional
import logging
import time

from matsim import versions

logger = logging.getLogger(__name__)


class MATSimRunner:
    """Run MATSim simulations"""

    DEFAULT_HEAP_RAM_FRACTION = 0.70

    def __init__(self, config: Dict):
        """
        Initialize MATSim runner

        Args:
            config: Main configuration dictionary from config.json
        """
        self.config = config
        self.matsim_config = config.get('matsim', {})
        self.os_type = platform.system()

    @staticmethod
    def _clamp_heap_to_ram(requested_gb: int, ram_fraction: float = None) -> int:
        """Cap the requested -Xmx (GB) at a fraction of physical RAM.

        The simulation is launched with -Xms equal to -Xmx, so the JVM reserves
        the whole heap at startup and fails outright ("Could not reserve enough
        space for object heap") when the config asks for more than the machine
        has. Clamping keeps a config written for a large machine usable on a
        smaller one while leaving headroom for the OS and Python. Never goes
        below 2g. Falls back to the requested value if RAM can't be determined.
        Mirrors NetworkGenerator._clamp_heap_to_ram.

        The default 70% suits a shared machine. On a dedicated host running one
        simulation, matsim.heap_ram_fraction can raise it -- at full population
        the heap is the binding constraint and the spare RAM is otherwise idle.
        Values above ~0.90 risk the OS OOM-killing the JVM, which dies silently.
        """
        if ram_fraction is None:
            ram_fraction = MATSimRunner.DEFAULT_HEAP_RAM_FRACTION
        ram_fraction = min(max(float(ram_fraction), 0.10), 0.90)
        try:
            import psutil
            total_gb = psutil.virtual_memory().total / (1024 ** 3)
            safe_cap = max(2, int(total_gb * ram_fraction))
            if requested_gb > safe_cap:
                logger.warning(
                    f"heap_size_gb={requested_gb}g exceeds {ram_fraction:.0%} of physical RAM "
                    f"({total_gb:.1f}g); clamping to {safe_cap}g."
                )
                return safe_cap
        except Exception as e:
            logger.debug(f"Could not determine RAM for heap clamp: {e}")
        return requested_gb

    def get_jar_path(self) -> Path:
        """Return the MATSim jar of matsim.version (see matsim/versions.py)."""
        jar_path = versions.get_jar_path(versions.get_version(self.matsim_config))
        logger.info(f"Using JAR file: {jar_path}")
        return jar_path

    def get_lib_path(self) -> Optional[Path]:
        """Return the *_lib folder of matsim.version, or None (shaded jar)."""
        lib_path = versions.get_lib_path(versions.get_version(self.matsim_config))
        if lib_path is not None:
            logger.info(f"Using lib directory: {lib_path}")
        return lib_path

    def build_classpath(self) -> str:
        """Jar plus <lib>/* when the version has a lib folder."""
        return versions.build_classpath(versions.get_version(self.matsim_config),
                                        self.os_type)

    def get_java_executable(self) -> str:
        """Java binary for matsim.version; raises if the release is too old."""
        return versions.resolve_java(self.matsim_config)

    def build_command(self, config_path: Path) -> list:
        """
        Build Java command to run MATSim

        Args:
            config_path: Path to config.xml file

        Returns:
            Command as list of strings
        """
        classpath = self.build_classpath()
        heap_size = self._clamp_heap_to_ram(
            self.matsim_config.get('heap_size_gb', 32),
            self.matsim_config.get('heap_ram_fraction'),
        )

        # Build command with JVM performance optimizations
        # Note: These are JVM flags, not MATSim arguments
        java = self.get_java_executable()
        version = versions.get_version(self.matsim_config)
        versions.check_java_for_version(java, version)
        logger.info(f"MATSim version: {version} "
                    f"({versions.MATSIM_VERSIONS.get(version, {}).get('release', '?')}), "
                    f"Java {versions.java_release(java)} at {java}")
        cmd = [
            java,
            f'-Xmx{heap_size}g',  # Maximum heap size
            f'-Xms{heap_size}g',  # Initial heap size (same as max to avoid resizing)
            '-XX:+UseG1GC',  # G1 garbage collector (recommended for heaps > 4GB)
            '-XX:+ParallelRefProcEnabled',  # Parallel reference processing
            '-XX:MaxGCPauseMillis=200',  # Target max GC pause time (200ms)
            '-XX:+HeapDumpOnOutOfMemoryError',  # Create heap dump on OOM
            '-XX:HeapDumpPath=./heap_dumps',  # Where to save heap dumps
            '-cp', classpath,
            *versions.main_args(version),
            str(config_path.resolve())
        ]

        return cmd

    def run_simulation(
        self,
        config_path: Path,
        log_file: Optional[Path] = None,
        blocking: bool = True
    ) -> subprocess.Popen:
        """
        Run MATSim simulation

        Args:
            config_path: Path to config.xml file
            log_file: Optional path to log file for simulation output
            blocking: If True, wait for simulation to complete

        Returns:
            Subprocess handle
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        logger.info(f"Starting MATSim simulation with config: {config_path}")

        # Build command
        cmd = self.build_command(config_path)

        # Log command
        logger.info(f"Command: {' '.join(cmd)}")

        # Prepare output streams
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            stdout_file = open(log_file, 'w')
            stderr_file = subprocess.STDOUT
        else:
            stdout_file = subprocess.PIPE
            stderr_file = subprocess.PIPE

        # Run simulation
        start_time = time.time()

        try:
            process = subprocess.Popen(
                cmd,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                cwd=config_path.parent  # Run from experiment directory
            )

            if blocking:
                logger.info("Waiting for simulation to complete...")
                return_code = process.wait()

                elapsed_time = time.time() - start_time
                logger.info(f"Simulation completed in {elapsed_time:.2f} seconds")

                if return_code == 0:
                    logger.info("Simulation completed successfully")
                else:
                    logger.error(f"Simulation failed with return code: {return_code}")
                    if not log_file:
                        stdout, stderr = process.communicate()
                        if stdout:
                            logger.error(f"STDOUT: {stdout}")
                        if stderr:
                            logger.error(f"STDERR: {stderr}")

                if log_file and isinstance(stdout_file, type(open(__file__))):
                    stdout_file.close()

            return process

        except Exception as e:
            logger.error(f"Failed to run simulation: {e}")
            if log_file and isinstance(stdout_file, type(open(__file__))):
                stdout_file.close()
            raise

    def check_java_version(self) -> Dict:
        """Find the Java binary for matsim.version and check its release.

        Returns:
            Dictionary with 'installed', 'java', 'version' (release number),
            'status' and, on error, 'error' (the reason).
        """
        try:
            java = self.get_java_executable()
        except RuntimeError as e:
            logger.error(str(e))
            return {'installed': False, 'java': None, 'version': None,
                    'status': 'error', 'error': str(e)}
        release = versions.java_release(java)
        if release is None:
            msg = f"Java not found or not working: {java}. Install Java to run MATSim."
            logger.error(msg)
            return {'installed': False, 'java': java, 'version': None,
                    'status': 'error', 'error': msg}
        logger.info(f"Java version: {release} ({java})")
        return {'installed': True, 'java': java, 'version': release, 'status': 'ok'}

    def validate_setup(self) -> bool:
        """
        Validate that all required components are available

        Returns:
            True if valid, False otherwise
        """
        logger.info("Validating MATSim setup...")

        # Check Java
        java_info = self.check_java_version()
        if not java_info['installed']:
            return False

        # Check JAR file
        try:
            jar_path = self.get_jar_path()
            if not jar_path.exists():
                logger.error(f"JAR file not found: {jar_path}")
                return False
        except Exception as e:
            logger.error(f"Failed to locate JAR file: {e}")
            return False

        # Check lib directory (matsim_25 is one shaded jar and has none)
        try:
            lib_path = self.get_lib_path()
            if lib_path and not lib_path.exists():
                logger.warning(f"Lib directory not found: {lib_path} (may not be needed)")
            elif lib_path:
                logger.info(f"Lib directory found: {lib_path}")
        except Exception as e:
            logger.warning(f"Could not check lib directory: {e} (may not be needed)")

        logger.info("MATSim setup validation passed")
        return True
