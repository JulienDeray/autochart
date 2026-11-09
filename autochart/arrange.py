"""Arrangement: chord shapes, sustains, lanes and the four difficulties.

**Shapes and sustains.** A note is sustained when the next note is at least 3/4 beat away and the guitar
is still ringing after 0.6 beat (reproduces official sustains with F1 0.85-1.0 when the rhythm is given).
Power chords become 2-note chords; accented or "stab" chords that ring for ~2 beats become 3-note chords.

**Lanes.** Five frets can't represent pitch, only *movement*. The goals are (a) up in pitch = right on the
highway, locally; (b) the same chord on the same lane wherever possible, so a riff looks the same each
time it comes back. Each root gets a preferred lane from its place in the song's pitch range (5th..95th
percentile mapped to the lanes). Then, per 2-bar block, the block's distinct roots get strictly
increasing lanes that minimise sum(count x |lane - preferred lane|) - an exact search, at most C(5,4)
cases. Identical blocks therefore always get identical lanes.

**Difficulties.** Official charts at any tempo keep roughly: Hard = 8ths, Medium = one note per beat,
Easy = one per two beats (measured on Harmonix/Neversoft charts). Notes are ranked by musical priority
(downbeat > beat > 8th > 16th, accents, pitch changes, held notes) and kept greedily while respecting a
minimum gap; important notes (pitch change, accent, sustain) may use a tighter gap. Medium uses 4 lanes
and only keeps chords that have a beat of space around them, Easy uses 3 lanes and no chords.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np

from .params import RES, Params


def shape_events(events: list[dict], period: float, p: Params) -> list[dict]:
    for e in events:
        held = e["ring_end"] - e["t"]
        e["sus_t"] = 0.0
        if e["next_tick"] - e["tick"] >= p.sustain_min_gap_beats * RES and held >= p.sustain_min_ring_beats * period:
            e["sus_t"] = held
        big = e["sus_t"] >= p.big_chord_ring_beats * period
        width = 1
        if e["power"]:
            width = 3 if (e["accent"] and big) else 2
        if e["stab"]:  # the "boom" hits of a riff are always chords
            width = max(width, 3 if big else 2)
        e["width"] = width
    return events


def assign_lanes(events: list[dict], max_lanes: int = 5, key: str = "lane", width_key: str = "width",
                 block_bars: int = 2) -> list[dict]:
    if not events:
        return events
    cap = max_lanes - (1 if max(e[width_key] for e in events) > 1 else 0)  # room for a 2-note chord
    allp = np.array([e["midi"] for e in events], float)
    lo, hi = np.percentile(allp, 5), np.percentile(allp, 95)
    hi = max(hi, lo + 1)

    def pref(q):
        return float(np.clip((q - lo) / (hi - lo) * (cap - 1), 0, cap - 1))

    blocks: dict[int, list] = {}
    for e in events:
        blocks.setdefault(e["tick"] // (block_bars * 4 * RES), []).append(e)
    cache: dict = {}
    for b in sorted(blocks):
        evs = blocks[b]
        cnt: dict[int, int] = {}
        for e in evs:
            cnt[e["midi"]] = cnt.get(e["midi"], 0) + 1
        keep = sorted(sorted(sorted(cnt), key=lambda q: -cnt[q])[:cap])  # too many roots: most frequent (ties: lower)
        sig = tuple((q, cnt[q]) for q in keep)
        if sig not in cache:
            best, best_c = None, None
            for lanes in combinations(range(cap), len(keep)):
                c = sum(cnt[q] * abs(ln - pref(q)) for q, ln in zip(keep, lanes))
                for i in range(len(keep) - 1):  # wide intervals deserve a visible jump
                    if keep[i + 1] - keep[i] >= 5 and lanes[i + 1] - lanes[i] == 1:
                        c += 0.3  # (added one by one: exact ties are common, keep float order stable)
                if best_c is None or c < best_c:
                    best, best_c = lanes, c
            cache[sig] = dict(zip(keep, best))
        mp = cache[sig]
        for e in evs:
            q = e["midi"] if e["midi"] in mp else min(keep, key=lambda x: (abs(x - e["midi"]), x))
            e[key] = mp[q]
    return events


def _priority(e, prev_midi):
    pr = {0: 4.0, 1: 3.0, 2: 1.5, 3: 0.0}[e["mc"]]
    pr += 2.0 * e["accent"] + 0.8 * e["strength"]
    pr += 2.0 * (prev_midi is not None and e["midi"] != prev_midi)
    pr += 1.5 * (e["sus_t"] > 0)
    return pr


def reduce(events: list[dict], level: str, p: Params) -> list[tuple[int, list[int], int]]:
    """Notes of one difficulty as (tick, [frets], sustain_ticks)."""
    cfg = p.difficulties[level]
    if level == "Expert":
        chosen = list(events)
    else:
        prev, last = {}, None
        for e in events:
            prev[id(e)], last = last, e["midi"]
        taken, chosen = [], []
        for e in sorted(events, key=lambda e: -_priority(e, prev[id(e)])):
            imp = e["accent"] or e["sus_t"] > 0 or (prev[id(e)] is not None and prev[id(e)] != e["midi"])
            gk = cfg["gap_k_imp"] if imp else cfg["gap_k"]
            if all(abs(e["t"] - t) >= cfg["gap_s"] - 1e-6 and abs(e["tick"] - k) >= gk
                   for t, k in taken if abs(e["t"] - t) < 2.0):
                taken.append((e["t"], e["tick"]))
                chosen.append(e)
        chosen.sort(key=lambda e: e["tick"])
        if level == "Hard":  # fast same-chord chugs: drop unaccented off-beats
            chosen = [e for i, e in enumerate(chosen)
                      if not (i > 0 and chosen[i - 1]["midi"] == e["midi"] and e["tick"] - chosen[i - 1]["tick"] <= RES // 2
                              and e["mc"] >= 2 and not e["accent"] and e["next_t"] - e["t"] < 0.22)]
    res = []
    for i, e in enumerate(chosen):
        w = min(e["width"], cfg["width"])
        if level == "Medium":
            nxt = chosen[i + 1]["tick"] if i + 1 < len(chosen) else e["tick"] + 4 * RES
            prv = chosen[i - 1]["tick"] if i > 0 else e["tick"] - 4 * RES
            if not (e["sus_t"] > 0 or (nxt - e["tick"] >= RES and e["tick"] - prv >= RES)):
                w = 1
        res.append(dict(e, w=w))
    if cfg["lanes"] < 5:
        assign_lanes(res, cfg["lanes"], key="lane_d", width_key="w")
    else:
        for e in res:
            e["lane_d"] = e["lane"] if e["lane"] + e["w"] - 1 <= 4 else 5 - e["w"]
    out = []
    for i, e in enumerate(res):
        nxt_tick = res[i + 1]["tick"] if i + 1 < len(res) else e["tick"] + 8 * RES
        sus = 0
        if e["sus_t"] > 0:
            sus_ticks = e["sus_t"] / max(e["next_t"] - e["t"], 1e-6) * (e["next_tick"] - e["tick"])
            sus_ticks = min(sus_ticks, nxt_tick - e["tick"] - RES // 4)
            sus = int(sus_ticks // (RES // 8)) * (RES // 8)
            if sus < RES // 4:
                sus = 0
        out.append((e["tick"], list(range(e["lane_d"], e["lane_d"] + e["w"])), sus))
    return out
