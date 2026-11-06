"""A recording Drive has not downloaded yet: its size is large but almost nothing is allocated on disk."""

import os
import random

from fixtures import formats as f

PARTIAL = "Planning - 2026-10-16 11.00 GMT+03.00 - Recording"
LOCAL = "Retro - 2026-10-17 15.00 GMT+03.00 - Recording"
DECLARED_SIZE = 50 * 1024 * 1024


def build(target):
    rng = random.Random(7)
    flat = target / "Meet Recordings"
    f.write_recording(flat, PARTIAL, [f.segment(0.0, 4.0, "Planning for the quokka launch.", rng)])
    os.truncate(flat / PARTIAL, DECLARED_SIZE)  # sparse: full size, one block allocated
    f.write_recording(flat, LOCAL, [f.segment(0.0, 3.0, "Retro: the walrus deploy went well.", rng)])
