"""Benchmarking against human charts.

Give it charts you trust (official Harmonix / Neversoft exports, or careful fan charts) as .sng files or
folders with their audio. Their audio stems are mixed back into one track, the generator runs on that
mix as if it were any song, and the result is compared with the human chart, difficulty by difficulty:

* **F1 (onsets)** - a generated note matches a human note within +-70 ms. Precision = share of our notes
  that the human also charted, recall = share of the human's notes we found.
* **contour** - on consecutive matched pairs: when the human moves up/down, do we move the same way
  ("change"), and when the human stays, do we stay ("same")? `contour_bal` is their mean. Raw fret
  agreement is meaningless (charters choose different hand positions), movement is what players feel.
* chord share and sustain share, ours vs theirs.
"""
from __future__ import annotations

import os
import re
import subprocess

import numpy as np

from . import audio, chartio, sng
from .chart import DIFF_ORDER
from .pipeline import analyse, safe_name
from .params import DEFAULT, Params

AUDIO_EXT = ("ogg", "opus", "mp3", "wav", "flac")


def match(a, b, tol=0.07):
    bt = np.array([x[0] for x in b])
    pairs, used = [], set()
    for i, x in enumerate(a):
        if not len(bt):
            break
        k = int(np.argmin(np.abs(bt - x[0])))
        if abs(bt[k] - x[0]) <= tol and k not in used:
            used.add(k)
            pairs.append((i, k))
    return pairs


def _direction(x, y):
    return int(np.sign(np.mean(y) - np.mean(x)))


def score(ref, gen) -> dict:
    """ref, gen: lists of (time_s, [frets], sustain_s, ...)."""
    pairs = match(ref, gen)
    prec, rec = len(pairs) / max(len(gen), 1), len(pairs) / max(len(ref), 1)
    ch = ch_ok = sm = sm_ok = 0
    for (i1, j1), (i2, j2) in zip(pairs, pairs[1:]):
        if i2 == i1 + 1 and j2 == j1 + 1:
            dh, da = _direction(ref[i1][1], ref[i2][1]), _direction(gen[j1][1], gen[j2][1])
            if dh == 0:
                sm, sm_ok = sm + 1, sm_ok + (da == 0)
            else:
                ch, ch_ok = ch + 1, ch_ok + (da == dh)
    share = lambda xs, f: round(float(np.mean([f(x) for x in xs])), 2) if xs else 0.0  # noqa: E731
    return {"n_ref": len(ref), "n_gen": len(gen), "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(2 * prec * rec / max(prec + rec, 1e-9), 3),
            "contour_change": round(ch_ok / max(ch, 1), 3), "contour_same": round(sm_ok / max(sm, 1), 3),
            "contour_bal": round((ch_ok / max(ch, 1) + sm_ok / max(sm, 1)) / 2, 3),
            "chords_ref": share(ref, lambda x: len(x[1]) > 1), "chords_gen": share(gen, lambda x: len(x[1]) > 1),
            "sustain_ref": share(ref, lambda x: x[2] > 0), "sustain_gen": share(gen, lambda x: x[2] > 0)}


def prepare(reference: str, cache_dir: str) -> tuple[str, str]:
    """Extract a reference .sng (or use a folder) and mix its audio stems -> (folder, mix_wav)."""
    name = safe_name(os.path.splitext(os.path.basename(reference.rstrip("/")))[0])
    if os.path.isdir(reference):
        folder = reference
    else:
        folder = os.path.join(cache_dir, "references", re.sub(r"\W+", "_", name))
        if not os.path.isdir(folder):
            sng.extract(reference, folder)
    mix = os.path.join(cache_dir, "references", re.sub(r"\W+", "_", name) + "__mix.wav")
    if not os.path.exists(mix):
        os.makedirs(os.path.dirname(mix), exist_ok=True)
        tracks = [os.path.join(folder, n) for n in sorted(os.listdir(folder))
                  if n.rsplit(".", 1)[-1].lower() in AUDIO_EXT and not n.startswith(("preview", "crowd"))]
        if not tracks:
            raise FileNotFoundError(f"no audio in {folder}")
        cmd = [audio.ffmpeg(), "-y", "-loglevel", "error"]
        for t in tracks:
            cmd += ["-i", t]
        if len(tracks) > 1:
            cmd += ["-filter_complex", f"amix=inputs={len(tracks)}:normalize=0"]
        subprocess.run(cmd + ["-ac", "2", "-ar", "44100", mix], check=True)
    return folder, mix


def _ini_delay(folder) -> float:
    p = os.path.join(folder, "song.ini")
    if not os.path.exists(p):
        return 0.0
    for line in open(p, encoding="utf-8", errors="replace"):
        k, _, v = line.partition("=")
        if k.strip().lower() == "delay":
            try:
                return float(v) / 1000
            except ValueError:
                return 0.0
    return 0.0


def evaluate(reference: str, cache_dir: str = "cache", p: Params = DEFAULT) -> dict:
    folder, mix = prepare(reference, cache_dir)
    stems = audio.separate(mix, cache_dir)
    grid, info, _, diffs = analyse(mix, stems, cache_dir, p)
    ref = chartio.load(folder)
    to_sec = lambda tick: float(np.interp(tick, grid.k, grid.t)) - grid.pad  # noqa: E731
    gen = {d: [(to_sec(t), lanes, (to_sec(t + s) - to_sec(t)) if s else 0.0, t) for t, lanes, s in diffs[d]]
           for d in DIFF_ORDER}
    delay = _ini_delay(folder)
    # song.ini delay conventions differ between tools: keep whichever sign aligns best
    best = max((1, -1, 0), key=lambda sgn: score([(t + sgn * delay, *r) for t, *r in ref["diffs"]["Expert"]],
                                                 gen["Expert"])["f1"])
    out = {"song": os.path.basename(reference), "bpm": round(info["bpm"], 2), "tempo_mode": info["mode"]}
    for d in DIFF_ORDER:
        out[d] = score([(t + best * delay, *r) for t, *r in ref["diffs"][d]], gen[d])
    return out
