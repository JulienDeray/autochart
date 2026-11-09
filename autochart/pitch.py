"""Pitch: which chord root each note plays.

Per note, the Basic Pitch *note posteriorgram* (probability of each MIDI pitch, 88 bins) of the guitar stem
is averaged over the first ~200 ms. A root `r` is scored with a power-chord template:

    root + 0.8 x fifth + 0.4 x octave - 0.5 x (r is the fifth of a lower root) - 0.3 x lower octave
    + 0.5 x bass-stem evidence for r's pitch class

The bass usually doubles the root, and the separated bass stem is much cleaner than a distorted guitar.

Scores are centred per note but scaled song-wide, so uncertain notes produce flat evidence; a Viterbi
pass then picks the most likely root *sequence* with a cost per root change. A repeated chord stays one
chord instead of flickering between D and A (its fifth), the main failure of the first version.

Distorted power chords are also often reported an octave off. `fold_octaves` keeps each root's pitch
class but moves it to the octave nearest the recent roots, so octave errors don't become lane jumps.
"""
from __future__ import annotations

import numpy as np

from .params import Params


def viterbi(E: np.ndarray, change_cost: float) -> list[int]:
    """Best state path for emission scores E (notes x states); each change costs `change_cost`,
    plus a tiny penalty proportional to the interval."""
    N, S = E.shape
    idx = np.arange(S)
    dist = np.abs(idx[:, None] - idx[None, :]).astype(float)
    T = -change_cost * (dist > 0) - 0.03 * change_cost * dist
    score, back = E[0].copy(), np.zeros((N, S), int)
    for i in range(1, N):
        cand = score[:, None] + T
        back[i] = np.argmax(cand, axis=0)
        score = cand[back[i], idx] + E[i]
    path = [int(np.argmax(score))]
    for i in range(N - 1, 0, -1):
        path.append(int(back[i][path[-1]]))
    return path[::-1]


def _window(post, times, e):
    a = np.searchsorted(times, e["t"] + 0.015)
    b = np.searchsorted(times, min(e["t"] + 0.22, e["next_t"] - 0.01))
    seg = post[a:max(b, a + 2)]
    return seg.mean(axis=0) if len(seg) else np.zeros(post.shape[1], np.float32)


def add_pitch(events: list[dict], guitar_bp, bass_bp, p: Params) -> list[dict]:
    """Sets e['midi'] (root) and e['power'] (power chord) on every event.
    guitar_bp / bass_bp: (note_posteriorgram [frames x 88, MIDI 21..108], frame_times)."""
    if not events:
        return events
    note, times = guitar_bp
    bnote, btimes = bass_bp
    roots = range(p.root_lo, p.root_hi + 1)
    sal, raw = [], []
    for e in events:
        bpc = np.zeros(12)
        bv = _window(bnote, btimes, e)
        for k in range(len(bv)):
            bpc[(k + 21) % 12] = max(bpc[(k + 21) % 12], bv[k])
        v = _window(note, times, e)
        m = lambda q: v[q - 21] if 21 <= q < 109 else 0.0  # noqa: E731
        sal.append([m(r) + 0.8 * m(r + 7) + 0.4 * m(r + 12) - 0.5 * m(r - 7) - 0.3 * m(r - 12)
                    + p.bass_weight * bpc[r % 12] for r in roots])
        raw.append(v)
    S = np.array(sal)
    Z = S - S.mean(1, keepdims=True)
    E = 3.0 * Z / (np.percentile(Z.max(1), 75) + 1e-6)
    for e, r, v in zip(events, viterbi(E, p.viterbi_change_cost), raw):
        root = p.root_lo + r
        rv, fifth = v[root - 21], (v[root + 7 - 21] if root + 7 < 109 else 0)
        e["midi"] = int(root)
        e["power"] = bool(fifth > p.power_ratio * max(rv, 1e-3) and fifth > p.power_min)
    return events


def fold_octaves(events: list[dict], win: int = 8, span: int = 9) -> list[dict]:
    """Move each root to the octave closest to the median of the last `win` roots (within +-span semitones
    of the song's median root)."""
    if not events:
        return events
    g = float(np.median([e["midi"] for e in events]))
    hist = []
    for e in events:
        pc = e["midi"] % 12
        ref = float(np.median(hist[-win:])) if hist else g
        ref = min(max(ref, g - span + 3), g + span - 3)
        cands = [pc + 12 * k for k in range(1, 8) if g - span <= pc + 12 * k <= g + span + 3] \
            or [pc + 12 * round((g - pc) / 12)]
        best = min(cands, key=lambda c: abs(c - ref))
        e["midi_raw"], e["midi"] = e["midi"], int(best)
        hist.append(best)
    return events
