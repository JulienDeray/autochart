"""Onsets: which 16th-note slots get a note.

Every slot of the beat grid is a candidate. A slot becomes a note when either

* the **guitar spectral flux** (Demucs guitar stem) has an attack there, normalised against the local
  +-2 bar range so quiet verses and loud choruses are judged alike, or
* **Basic Pitch** reports a note onset there (it catches pitch changes that have no loud attack: legato,
  slides, chord changes under a wall of distortion).

Thresholds depend on the metric position: downbeats need little evidence, isolated 16ths need a lot and
must be a local peak. Then:

* **Big stabs**: an attack much louder than the song's usual (>= 1.5 x its 95th percentile) is the
  "boom" chord of a riff. Basic Pitch keeps firing while that chord rings, and the filler buried the hit.
  Around each stab, weak notes are removed - only where the guitar is ringing, i.e. shows no 8th-note
  picking pulse, so genuine chugs between accents survive.
* **Smears**: a pitch-only note one 16th before a much louder real attack is the same hit seen twice;
  only the attack is kept.
* For each kept note: how long the guitar keeps ringing (sustains), and whether it is accented.
"""
from __future__ import annotations

import librosa
import numpy as np

from .grid import Grid, metric_class
from .params import RES, Params

HOP = 128


def detect_events(y_g: np.ndarray, sr: int, grid: Grid, bp_onsets, p: Params) -> list[dict]:
    """y_g: guitar stem. bp_onsets: (onset_posteriorgram [frames x 88], frame_times) from Basic Pitch."""
    env = librosa.onset.onset_strength(y=y_g, sr=sr, hop_length=HOP, aggregate=np.mean, lag=1, max_size=3)
    et = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=HOP)
    rms = librosa.amplitude_to_db(librosa.feature.rms(y=y_g, hop_length=HOP)[0], ref=np.max)
    st, ticks = grid.slot_times(4)
    ok = (st > 0) & (st < et[-1] - 0.05)
    st, ticks = st[ok], ticks[ok]
    if not len(st):
        return []

    # flux at each slot; the envelope lags the attack, hence the asymmetric window
    val = np.array([env[(et > t - 0.02) & (et < t + 0.045)].max(initial=0) for t in st])
    level = np.interp(st + 0.04, et, rms)
    norm = np.empty_like(val)
    for i in range(len(val)):  # local normalisation over +-2 bars
        w = val[max(0, i - 32):i + 33]
        lo, hi = np.percentile(w, 25), np.percentile(w, 95)
        norm[i] = (val[i] - lo) / max(hi - lo, 1e-6)
    absv = val / (np.percentile(val, 95) + 1e-9)  # song-wide scale, for stabs

    onset, btimes = bp_onsets
    omax = onset[:, 7:68].max(axis=1)  # MIDI 28..88
    bpv = np.array([omax[(btimes > t - 0.02) & (btimes < t + 0.05)].max(initial=0) for t in st])

    # picking pulse: flux on beats/8ths vs on off-16ths, over +-1 bar. Picked 8ths show a strong ratio.
    is8 = np.array([metric_class(int(k)) <= 2 for k in ticks])
    ratio8 = np.ones_like(val)
    for i in range(len(val)):
        a, b = max(0, i - 16), min(len(val), i + 17)
        v8, v16 = val[a:b][is8[a:b]], val[a:b][~is8[a:b]]
        ratio8[i] = (v8.mean() + 1e-9) / (v16.mean() + 1e-9) if len(v8) and len(v16) else 9.0

    slow = grid.bpm < p.slow_bpm
    sig = np.maximum(norm, bpv)
    events = []
    for i, (t, tk) in enumerate(zip(st, ticks)):
        if level[i] < p.silence_db:
            continue
        mc = metric_class(int(tk))
        mt = mc - 1 if (slow and mc >= 2) else mc  # at 90 BPM a 16th lasts as long as an 8th at 180
        flux_ok = norm[i] >= p.flux_threshold[mt]
        bp_ok = bpv[i] >= p.bp_threshold[mt]
        if not (flux_ok or bp_ok):
            continue
        if mc == 3 and ((i > 0 and sig[i] < sig[i - 1]) or (i + 1 < len(sig) and sig[i] < sig[i + 1])):
            continue  # an isolated 16th must be a local peak
        stab = bool(flux_ok and absv[i] >= p.stab_level)
        events.append({"t": float(t), "tick": int(tk), "mc": mc, "strength": float(norm[i]), "flux": bool(flux_ok),
                       "abs": float(absv[i]), "r8": float(ratio8[i]), "stab": stab})

    events = _clean_around_stabs(events, p)
    events = _drop_smears(events, p)
    _measure_ring(events, et, rms)
    _mark_accents(events)
    return events


def _clean_around_stabs(events, p: Params):
    drop = set()
    for s in (e for e in events if e["stab"]):
        floor = p.stab_floor * s["abs"]
        strong = [e["tick"] for e in events if e["abs"] >= floor]
        nxt = next((k for k in strong if k > s["tick"]), s["tick"] + 4 * RES)
        prv = max((k for k in strong if k < s["tick"]), default=s["tick"] - 4 * RES)
        start, end = max(prv, s["tick"] - 4 * RES), min(nxt, s["tick"] + 4 * RES)
        for e in events:
            if e["abs"] < floor and e["r8"] < p.stab_ring_ratio and (
                    start < e["tick"] < s["tick"] or s["tick"] < e["tick"] < end):
                drop.add(id(e))
    return [e for e in events if id(e) not in drop]


def _drop_smears(events, p: Params):
    """A Basic-Pitch-only note (no flux attack) one 16th before a clearly louder real attack that lands on
    an off-16th is the same hit seen twice: the pitch model fires on the chord, the guitar lands just after
    the beat. Charting both gave a double hit on the first chord of a riff. Keep the real attack."""
    keep = []
    for j, e in enumerate(events):
        nx = events[j + 1] if j + 1 < len(events) else None
        if (not e["flux"] and nx is not None and nx["flux"] and nx["mc"] == 3
                and 0 < nx["tick"] - e["tick"] <= RES // 4
                and nx["abs"] >= p.smear_ratio * max(e["abs"], 1e-6)):
            continue
        keep.append(e)
    return keep


def _measure_ring(events, et, rms):
    """next note time/tick, and ring_end: when the guitar level falls 9 dB below the attack."""
    for j, e in enumerate(events):
        nxt_t = events[j + 1]["t"] if j + 1 < len(events) else e["t"] + 2.0
        e["next_t"] = nxt_t
        e["next_tick"] = events[j + 1]["tick"] if j + 1 < len(events) else e["tick"] + 4 * RES
        a, b = np.searchsorted(et, e["t"] + 0.03), np.searchsorted(et, nxt_t - 0.02)
        seg = rms[a:max(b, a + 1)]
        peak = seg[:8].max() if len(seg) else -80
        below = np.flatnonzero(seg < peak - 9)
        e["ring_end"] = float(et[a + below[0]]) if len(below) else float(nxt_t)


def _mark_accents(events):
    s = np.array([e["strength"] for e in events]) if events else np.array([])
    for j, e in enumerate(events):
        loc = np.median(s[max(0, j - 16):j + 17])
        e["accent"] = bool((e["strength"] > 1.35 * loc and e["strength"] > 0.8) or e["stab"])

