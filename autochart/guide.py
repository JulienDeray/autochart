"""Player guide: chart a song the way *you* play it, from Alfred Tapper recordings (tools/tapper.html).

You play the song 2-3 times on the keyboard (keys 1-5 = frets). From those passes:

* **Strums**: key-downs within 45 ms are one strum (a chord if several keys).
* **Consensus**: a strum counts when at least two passes have one within 70 ms. Its time is the median,
  its lanes the most frequent shape, its hold the median key-down length.
* **Windows** of 2 bars:
  - *held* windows: 2-5 strums, mostly held >= 1 beat. These are the big held chords. Your timing and your
    lanes are not trusted there (taps wobble ~90 ms and five keys can't say which chord it is); only *that*
    there is a big chord here, and roughly when. `refine_held` re-reads each chord from the audio.
  - *style* windows: >= 3 strums elsewhere. Your riff is reproduced as played: rhythm, lanes, single note or
    chord. Notes snap to the nearest 16th within 60 ms.
  - Windows where you played nothing are left to the automatic charter.

Measured caveat: against an official chart (Cherry Bomb, Harmonix) a tap-guided chart scores *lower*
(Expert F1 0.72 -> 0.61). It captures a player's taste, not official charting style.
"""
from __future__ import annotations

import json
from collections import Counter

import numpy as np

from .grid import Grid, metric_class
from .params import RES


# ------------------------------------------------------------------ taps -> guide
def strums(events: list[dict], gap: float = 0.045) -> list[dict]:
    out: list[dict] = []
    for e in sorted(events, key=lambda e: e["down"]):
        up = e.get("up") or e["down"]
        if out and e["down"] - out[-1]["t"] <= gap:
            out[-1]["lanes"].add(e["lane"])
            out[-1]["up"] = max(out[-1]["up"], up)
        else:
            out.append({"t": e["down"], "lanes": {e["lane"]}, "up": up})
    for s in out:
        s["hold"] = s["up"] - s["t"]
    return out


def consensus(passes: list[list[dict]], tol: float = 0.07) -> list[dict]:
    allst = sorted(((s, pi) for pi, p in enumerate(passes) for s in p), key=lambda x: x[0]["t"])
    clusters: list[dict] = []
    for s, pi in allst:
        if clusters and s["t"] - clusters[-1]["ts"][0] <= tol and pi not in clusters[-1]["passes"]:
            c = clusters[-1]
        else:
            c = {"ts": [], "passes": set(), "lanes": [], "holds": []}
            clusters.append(c)
        c["ts"].append(s["t"])
        c["passes"].add(pi)
        c["lanes"].append(tuple(sorted(s["lanes"])))
        c["holds"].append(s["hold"])
    need = 2 if len(passes) >= 2 else 1
    return [{"t": float(np.median(c["ts"])), "hold": float(np.median(c["holds"])),
             "lanes": list(Counter(c["lanes"]).most_common(1)[0][0])}
            for c in clusters if len(c["passes"]) >= need]


def _windows(cons, win, end, pred):
    out: list[list[float]] = []
    t = 0.0
    while t < end:
        ss = [s for s in cons if t <= s["t"] < t + win]
        if pred(t, ss):
            if out and abs(out[-1][1] - t) < 1e-6:
                out[-1][1] = t + win
            else:
                out.append([t, t + win])
        t += win
    return out


def build_guide(taps: dict, bpm: float) -> dict:
    """taps: an Alfred Tapper export ({"passes": [{"events": [{"lane", "down", "up"}]}]}). Times are audio
    seconds, already corrected by the tapper's calibration."""
    passes = [strums(p["events"]) for p in taps["passes"] if p.get("events")]
    if not passes:
        raise ValueError("the tapper file has no recorded passes")
    cons = consensus(passes)
    beat = 60.0 / bpm
    win = 8 * beat
    end = max((s["t"] for s in cons), default=0.0) + win
    held = _windows(cons, win, end, lambda t, ss: 2 <= len(ss) <= 5 and np.mean([s["hold"] >= beat for s in ss]) >= 0.5)
    style = _windows(cons, win, end, lambda t, ss: len(ss) >= 3 and not any(a <= t < b for a, b in held))
    return {"held": held, "style": style, "strums": cons, "passes": len(passes)}


def load_taps(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)
    if data.get("tool") != "alfred-tapper":
        raise ValueError(f"{path} is not an Alfred Tapper export")
    return data


# ------------------------------------------------------------------ guide -> events
def _note(t, tk, hold, **kw):
    e = {"t": float(t), "tick": int(tk), "mc": metric_class(int(tk)), "strength": 1.0, "flux": True, "abs": 1.0,
         "r8": 1.0, "hold": float(hold), "guided": True}
    e.update(kw)
    return e


def apply_guide(events: list[dict], guide: dict, grid: Grid, period: float) -> list[dict]:
    slot_t, slot_k = grid.slot_times(4)
    held, style = guide.get("held", []), guide.get("style", [])
    in_held = lambda t: any(a <= t < b for a, b in held)  # noqa: E731
    in_style = lambda t: any(a <= t < b for a, b in style)  # noqa: E731
    attack = {e["tick"]: e.get("abs", 0.0) for e in events}
    kept = [e for e in events if not in_held(e["t"]) and not in_style(e["t"])]

    def snap(t, radius, time_cost):
        c = np.flatnonzero(np.abs(slot_t - t) <= radius)
        if not len(c):
            return None
        j = max(c, key=lambda j: attack.get(int(slot_k[j]), 0.0) - time_cost * abs(slot_t[j] - t))
        return float(slot_t[j]), int(slot_k[j])

    last_h = last_s = -10 ** 9
    for st in guide.get("strums", []):
        if in_held(st["t"]):
            s = snap(st["t"], 0.11, 5)  # rough: refine_held finds the real start
            if s and s[1] - last_h > RES // 4:  # a chord split over two strums -> one note
                last_h = s[1]
                kept.append(_note(*s, st["hold"], stab=True, accent=True))
        elif in_style(st["t"]) and st.get("lanes"):
            s = snap(st["t"], 0.06, 15)
            if s and s[1] - last_s >= RES // 4:
                last_s = s[1]
                kept.append(_note(*s, st["hold"], stab=False, accent=len(st["lanes"]) > 1, fixed=sorted(st["lanes"])))
    kept.sort(key=lambda e: e["tick"])
    out: list[dict] = []
    for e in kept:  # one note per slot, the guide wins
        if out and out[-1]["tick"] == e["tick"]:
            if e.get("guided"):
                out[-1] = e
            continue
        out.append(e)
    _relink(out, period)
    return out


def _relink(events, period):
    for j, e in enumerate(events):
        e["next_t"] = events[j + 1]["t"] if j + 1 < len(events) else e["t"] + 2.0
        e["next_tick"] = events[j + 1]["tick"] if j + 1 < len(events) else e["tick"] + 4 * RES
        if e.get("guided"):
            # in riffs players keep keys down legato (~0.45 s): only a clearly long hold is a sustain
            need = 2.0 * period if e.get("fixed") else 0.6 * period
            e["ring_end"] = min(e["t"] + e["hold"], e["next_t"]) if e["hold"] > need else e["t"] + 0.05


def _pc_frames(post, lo, hi):
    P = np.zeros((post.shape[0], 12), np.float32)
    for m in range(lo, hi):
        P[:, m % 12] += post[:, m - 21]
    return P


def refine_held(events: list[dict], guitar_bp, bass_bp, grid: Grid, period: float) -> list[dict]:
    """Held chords: (1) which chord = bass + guitar power-chord pitch class over the WHOLE hold (the first
    0.2 s still carries the previous chord ringing, which mislabelled C/F as D/Eb and made lanes jump);
    (2) where it starts = the 16th within +-0.25 s of the tap that best separates 'not this chord' before
    from 'this chord' after; (3) a chord re-tapped within a beat is one chord. Sets e['root_pc']."""
    note, times = guitar_bp
    bnote, btimes = bass_bp
    G, B = _pc_frames(note, 28, 76), _pc_frames(bnote, 24, 60)
    slot_t, slot_k = grid.slot_times(4)

    def seg(P, tt, t0, t1):
        a, b = np.searchsorted(tt, t0), np.searchsorted(tt, t1)
        v = P[a:max(b, a + 1)].mean(0)
        return v / (v.max() + 1e-6)

    def prof(t0, t1):
        return seg(B, btimes, t0, t1) + 0.6 * seg(G, times, t0, t1)

    def root_pc(t0, t1):
        g, b = seg(G, times, t0, t1), seg(B, btimes, t0, t1)
        gr = np.array([g[c] + 0.8 * g[(c + 7) % 12] - 0.5 * g[(c - 7) % 12] for c in range(12)])
        return int(np.argmax(b + 0.6 * gr / (np.abs(gr).max() + 1e-6)))

    for e in (e for e in events if e.get("guided") and not e.get("fixed")):
        pc = root_pc(e["t"] + 0.15, min(e["next_t"], e["t"] + 2.5))
        best = None
        for j in np.flatnonzero(np.abs(slot_t - e["t"]) <= 0.25):
            t = slot_t[j]
            after, before = prof(t + 0.02, t + 0.3), prof(t - 0.3, t - 0.02)
            sc = after[pc] / (after.max() + 1e-6) - before[pc] / (before.max() + 1e-6) - 2.0 * abs(t - e["t"])
            if best is None or sc > best[0]:
                best = (sc, float(t), int(slot_k[j]))
        if best:
            e["t"], e["tick"], e["mc"] = best[1], best[2], metric_class(best[2])
        e["root_pc"] = pc
    events.sort(key=lambda e: e["tick"])
    out: list[dict] = []
    for e in events:
        if out and e.get("root_pc") is not None and out[-1].get("root_pc") == e["root_pc"] \
                and e["tick"] - out[-1]["tick"] < RES:
            continue
        if out and out[-1]["tick"] == e["tick"]:
            if e.get("guided"):
                out[-1] = e
            continue
        out.append(e)
    _relink(out, period)
    return out


def held_pitch(events: list[dict]) -> list[dict]:
    """After pitch analysis: held chords take their whole-hold root, one octave per chord song-wide."""
    held = [e for e in events if e.get("root_pc") is not None]
    if held:
        g = float(np.median([e["midi"] for e in events]))
        for e in held:
            e["midi"] = int(min((e["root_pc"] + 12 * k for k in range(2, 7)), key=lambda m: abs(m - g)))
            e["power"] = True
    return events


def held_lanes(events: list[dict]) -> list[dict]:
    """One chord -> lane map for all held chords of the song (same chord = same lanes, up = up), 2-note chords
    on lanes 0..3; the 4 most frequent chords are anchors, others take the nearest anchor's lane."""
    held = [e for e in events if e.get("root_pc") is not None]
    if not held:
        return events
    cnt = Counter(e["midi"] for e in held)
    anchors = sorted(sorted(cnt, key=lambda q: (-cnt[q], q))[:4])
    n = len(anchors)
    mp = {q: (1 if n == 1 else int(round(i * 3 / (n - 1)))) for i, q in enumerate(anchors)}
    for e in held:
        q = e["midi"] if e["midi"] in mp else min(anchors, key=lambda a: (abs(a - e["midi"]), a))
        e["lane"], e["width"] = mp[q], 2
    for e in events:
        if e.get("fixed"):
            e["lane"] = min(e["fixed"])
    return events
