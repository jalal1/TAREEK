# SPDX-License-Identifier: GPL-3.0-or-later
"""Repeatable random streams for plan generation.

Plan generation must give the same plans for the same config and
``plan_generation.random_seed``. Three things broke that before:

* ``hash(str)`` changes in each Python process (PYTHONHASHSEED), so a seed
  made from ``hash(purpose)`` changed in each run.
* ``np.random.default_rng()`` without a seed takes fresh OS entropy.
* Pool workers share the global ``np.random`` state in a way that depends on
  which worker gets which chunk, and ``imap_unordered`` returns chunks in the
  order they finish.

The fix is to derive every stream from the config seed plus stable keys
(purpose, origin, destination) with a hash that does not change between
processes, and to reseed at the start of each OD pair. Then the plans do not
depend on the number of processes or on the worker schedule.
"""

import zlib
from typing import Any

import numpy as np


def derive_seed(base_seed: int, *keys: Any) -> int:
    """Return a 32-bit seed from ``base_seed`` and ``keys``.

    The result is the same in every process and on every platform. Keys are
    converted with ``str()``, so ``'Work'`` and ``27003`` are both valid.
    """
    key_words = [zlib.crc32(str(k).encode('utf-8')) for k in keys]
    seq = np.random.SeedSequence([int(base_seed) & 0xFFFFFFFF, *key_words])
    return int(seq.generate_state(1, dtype=np.uint32)[0])


def reseed(base_seed: int, *keys: Any) -> np.random.Generator:
    """Seed the global ``np.random`` state and return a matching Generator.

    Much of the plan code (chain sampling, scipy KDE ``resample``, POI choice,
    location jitter) uses the global state, so both are set here.
    """
    seed = derive_seed(base_seed, *keys)
    np.random.seed(seed)
    return np.random.default_rng(seed)
