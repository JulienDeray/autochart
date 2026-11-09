"""Beat grid: where the beats are, in seconds.

Two candidate grids are built from the onset envelope of the *drum stem* and the one that explains the
drums better wins:

1. **Constant tempo** - an exhaustive search over (period, phase) of a perfectly regular grid. Most modern
   studio recordings are played to a click, and a constant grid is then far more accurate than any beat
   tracker (on the song that motivated this project, a per-beat tracker wandered between 148 and 246 BPM
   on a 180.0 BPM click track and drifted up to 350 ms).
2. **Tempo-following** - for recordings played without a click (older punk / rock records), a dynamic
   programming tracker with a slowly varying tempo prior, snapped to drum hits and smoothed on absolute
   beat times (never by re-integrating periods, which accumulates drift).

Quality of a grid = share of strong drum onsets that fall within 30 ms of its 8th-note positions. The
tempo-following grid must beat the constant one by 10 points to be chosen.

Finally the grid is shifted 20 ms earlier: spectral-flux onset envelopes peak 1-2 frames after the
perceived attack (measured +14..+26 ms against four hand-made tempo maps).
"""
from __future__ import annotations

import librosa
import numpy as np
from scipy.ndimage import median_filter, uniform_filter1d
from scipy.signal import savgol_filter

HOP = 256
LATENCY = 0.020  # seconds; see module docstring
# The tempo-following grid must explain this many more drum hits to be chosen. Measured gaps: live-played
# benchmark songs 0.15-0.45, click-track songs 0.00-0.05. At 0.05 a click-track song flipped mode
# depending on tiny separation differences, so the margin sits in the middle of the empty range.
VARIABLE_MARGIN = 0.10


def onset_env(y: np.ndarray, sr: int) -> np.ndarray:
    """Normalised onset-strength envelope with slow loudness changes removed."""
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median, lag=1, max_size=1)
    env = np.maximum(env - uniform_filter1d(env, 64), 0)
    return env / (np.percentile(env, 99) + 1e-9)


def _sample(env, times, sr):
    return np.interp(times * sr / HOP, np.arange(len(env)), env, left=0, right=0)


def _grid_score(env, sr, period, phase, n, weights=(1.0, 0.6, 0.25)):
    """How much onset energy a regular grid catches: beats, 8ths and 16ths with decreasing weights."""
    b = phase + np.arange(n) * period
    s = weights[0] * _sample(env, b, sr).sum()
    s += weights[1] * _sample(env, b + period / 2, sr).sum()
    s += weights[2] * (_sample(env, b + period / 4, sr).sum() + _sample(env, b + 3 * period / 4, sr).sum())
    return s


def fit_constant(env, sr, dur, period0):
    """Exhaustive (period +-3 %, phase) search around a first tempo guess, then a fine refinement."""
    best = (-1.0, period0, 0.0)
    for period in np.linspace(period0 * 0.97, period0 * 1.03, 241):
        n = int(dur / period)
        for phase in np.arange(0, period, 0.004):
            s = _grid_score(env, sr, period, phase, n)
            if s > best[0]:
                best = (s, period, phase)
    _, period, phase = best
    for period_ in np.linspace(period * 0.999, period * 1.001, 41):
        n = int(dur / period_)
        for phase_ in np.arange(phase - 0.006, phase + 0.006, 0.0005):
            s_ = _grid_score(env, sr, period_, phase_, n)
            if s_ > best[0]:
                best = (s_, period_, phase_)
    return best[1], best[2] % best[1]


def track_variable(env, sr, period0, dur):
    """Tempo-following beats for recordings without a click track."""
    bpm0 = 60.0 / period0
    tc = librosa.feature.tempo(onset_envelope=env, sr=sr, hop_length=HOP, aggregate=None, start_bpm=bpm0,
                               std_bpm=0.15, max_tempo=bpm0 * 1.25)
    tc = median_filter(tc, size=int(8 * sr / HOP) | 1, mode="nearest")
    _, beats = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=HOP, bpm=tc, tightness=300,
                                       units="time", trim=False)
    beats = np.asarray(beats, float)
    fr = np.arange(len(env)) * HOP / sr
    snapped = []
    for b in beats:  # snap to the strongest drum hit within +-35 ms
        m = (fr > b - 0.035) & (fr < b + 0.035)
        snapped.append(fr[m][np.argmax(env[m])] if m.any() and env[m].max() > 0.2 else b)
    snapped = np.array(snapped)
    if len(snapped) > 15:
        snapped = savgol_filter(snapped, 13, 2)
    p0, p1 = np.median(np.diff(snapped[:9])), np.median(np.diff(snapped[-9:]))
    head = np.arange(snapped[0] - p0, 0, -p0)[::-1]
    tail = np.arange(snapped[-1] + p1, dur + p1, p1)
    return np.concatenate([head, snapped, tail])


def grid_fit_quality(env, sr, beats) -> float:
    """Share of strong drum onsets within 30 ms of the grid's beats or 8th notes."""
    fr = np.arange(len(env)) * HOP / sr
    peaks = librosa.util.peak_pick(env, pre_max=3, post_max=3, pre_avg=10, post_avg=10, delta=0.15, wait=4)
    pt = fr[peaks]
    pt = pt[(pt > beats[0]) & (pt < beats[-1])]
    grid = np.sort(np.concatenate([beats, beats[:-1] + np.diff(beats) / 2]))
    if not len(pt):
        return 0.0
    d = np.array([np.min(np.abs(grid - t)) for t in pt])
    return float(np.mean(d < 0.03))


def beat_grid(y_drums, y_mix, sr, start_bpm=160):
    """Return (beat_times, info). info: bpm, mode ('constant' | 'variable'), fit_constant, fit_variable."""
    dur = len(y_mix) / sr
    use_drums = y_drums is not None and np.abs(y_drums).max() > 1e-3
    env = onset_env(y_drums if use_drums else y_mix, sr)
    _, beats_tr = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=HOP, start_bpm=start_bpm,
                                          tightness=100, units="time")
    if len(beats_tr) < 8:
        raise RuntimeError("beat tracking failed: fewer than 8 beats found (is there any rhythm?)")
    period, phase = fit_constant(env, sr, dur, float(np.median(np.diff(beats_tr))))
    beats = np.arange(phase, dur + period, period)
    q_const = grid_fit_quality(env, sr, beats)
    beats_v = track_variable(env, sr, period, dur)
    q_var = grid_fit_quality(env, sr, beats_v)
    info = {"bpm": 60 / period, "phase": phase, "fit_constant": round(q_const, 3), "fit_variable": round(q_var, 3),
            "mode": "constant", "drums_used": bool(use_drums)}
    if q_var > q_const + VARIABLE_MARGIN:
        beats = beats_v
        info["mode"] = "variable"
        info["bpm"] = 60 / float(np.median(np.diff(beats_v)))
    return beats - LATENCY, info
