"""Tunable constants, in one place.

Every value below was chosen by measurement against hand-made / official charts (see docs/EVALUATION.md),
not by ear. Change them only with the benchmark at hand.
"""
from __future__ import annotations

from dataclasses import dataclass, field

RES = 192          # chart ticks per beat (Moonscraper / Clone Hero default)
SR = 22050         # analysis sample rate
STEMS = ("guitar", "bass", "drums", "vocals", "other", "piano")  # htdemucs_6s outputs


@dataclass(frozen=True)
class Params:
    # --- onsets (one candidate per 16th-note slot; metric position: bar, beat, 8th, 16th)
    flux_threshold: tuple = (0.15, 0.15, 0.20, 0.60)   # locally normalised guitar spectral flux
    bp_threshold: tuple = (0.40, 0.40, 0.50, 0.80)     # Basic Pitch onset probability
    silence_db: float = -45.0                          # guitar stem level gate (dB below its peak)
    slow_bpm: float = 100.0                            # below: judge 16ths like 8ths
    stab_level: float = 1.5                            # attack >= 1.5 x the song's p95 flux = a "big stab"
    stab_floor: float = 0.3                            # notes weaker than 0.3 x the stab are filler...
    stab_ring_ratio: float = 1.6                       # ...if the guitar shows no 8th picking pulse there
    # --- pitch
    root_lo: int = 28                                  # E1: lowest candidate root (detuned guitars)
    root_hi: int = 67                                  # G4
    viterbi_change_cost: float = 0.6                   # higher = roots change less often
    bass_weight: float = 0.5                           # vote of the bass stem for the root's pitch class
    power_ratio: float = 0.6                           # fifth >= 0.6 x root -> power chord
    power_min: float = 0.15
    # --- sustains / chords
    sustain_min_gap_beats: float = 0.75
    sustain_min_ring_beats: float = 0.6
    big_chord_ring_beats: float = 1.8                  # accented chords ringing this long get 3 notes
    # --- lanes
    lane_block_bars: int = 2
    # --- difficulties: min gap between kept notes (seconds, ticks), tighter "important" gap, lanes, width
    difficulties: dict = field(default_factory=lambda: {
        "Expert": dict(gap_s=0.0, gap_k=RES // 4, gap_k_imp=RES // 4, lanes=5, width=3),
        "Hard": dict(gap_s=0.14, gap_k=RES // 2, gap_k_imp=RES // 2, lanes=5, width=2),
        "Medium": dict(gap_s=0.25, gap_k=RES, gap_k_imp=RES // 2, lanes=4, width=2),
        "Easy": dict(gap_s=0.45, gap_k=2 * RES, gap_k_imp=RES, lanes=3, width=1),
    })


DEFAULT = Params()
