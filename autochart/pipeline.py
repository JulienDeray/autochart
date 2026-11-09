"""The whole pipeline: audio file -> playable YARG / Clone Hero song."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass

import librosa

from . import __version__, arrange, audio, beatgrid, chart, onsets, pitch, sng
from .chart import DIFF_ORDER
from .grid import Grid
from .params import DEFAULT, SR, STEMS, Params


@dataclass
class Result:
    path: str           # .sng file or song folder
    meta: dict          # tempo, counts, ... (also written as autochart.json in folder mode)
    events: list        # Expert-level note events with all analysis fields (for debugging)


def analyse(audio_path: str, stems: dict[str, str], cache_dir: str, p: Params = DEFAULT):
    """Everything except writing files. Returns (grid, beat_info, events, difficulties)."""
    y_mix, sr = librosa.load(audio_path, sr=SR, mono=True)
    y_drums, _ = librosa.load(stems["drums"], sr=SR, mono=True)
    y_gtr, _ = librosa.load(stems["guitar"], sr=SR, mono=True)
    beats, info = beatgrid.beat_grid(y_drums, y_mix, sr)
    period = 60.0 / info["bpm"]
    grid = Grid(beats, period)
    g_note, g_onset, g_times = audio.posteriorgrams(stems["guitar"], cache_dir)
    b_note, _, b_times = audio.posteriorgrams(stems["bass"], cache_dir)
    events = onsets.detect_events(y_gtr, sr, grid, (g_onset, g_times), p)
    if not events:
        raise RuntimeError("no guitar notes detected: is there a guitar in this song?")
    events = pitch.add_pitch(events, (g_note, g_times), (b_note, b_times), p)
    events = pitch.fold_octaves(events)
    events = arrange.shape_events(events, period, p)
    events = arrange.assign_lanes(events, block_bars=p.lane_block_bars)
    diffs = {lvl: arrange.reduce(events, lvl, p) for lvl in DIFF_ORDER}
    info["duration"] = len(y_mix) / sr
    return grid, info, events, diffs


def safe_name(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")


def generate(audio_path: str, artist: str, title: str, out_dir: str = ".", *, cache_dir: str = "cache",
             album: str = "", year: str = "", genre: str = "Rock", charter: str = "autochart",
             fmt: str = "sng", stems: dict[str, str] | None = None, render: bool = True,
             p: Params = DEFAULT) -> Result:
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"audio file not found: {audio_path}")
    if fmt not in ("sng", "folder"):
        raise ValueError("fmt must be 'sng' or 'folder'")
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    if render:
        audio.ffmpeg()  # fail early, before minutes of separation
    stems = stems or audio.separate(audio_path, cache_dir)
    missing = [s for s in STEMS if s not in stems or not os.path.exists(stems[s])]
    if missing:
        raise FileNotFoundError(f"missing stems: {missing}")
    grid, info, events, diffs = analyse(audio_path, stems, cache_dir, p)

    charter_full = f"{charter} (autochart {__version__})"
    meta = {"autochart": __version__, "pad": round(grid.pad, 4), **info, "notes": {k: len(v) for k, v in diffs.items()},
            "chords_expert": round(sum(len(l) > 1 for _, l, _ in diffs["Expert"]) / max(len(diffs["Expert"]), 1), 2)}
    name = safe_name(f"{artist} - {title}")
    work = tempfile.mkdtemp(prefix="autochart-")
    try:
        const = round(info["bpm"], 3) if info["mode"] == "constant" else None
        chart.write_chart(os.path.join(work, "notes.chart"), title, artist, charter_full, grid.sync_lines(const), diffs)
        chart.write_ini(os.path.join(work, "song.ini"), title=title, artist=artist, album=album, year=year,
                        genre=genre, charter=charter_full, length_ms=int((info["duration"] + grid.pad) * 1000))
        if render:
            audio.render(stems, grid.pad, work)
        if fmt == "sng":
            dst = os.path.join(out_dir, name + ".sng")
            sng.pack_folder(work, dst)
        else:
            with open(os.path.join(work, "autochart.json"), "w") as f:
                json.dump(meta, f, indent=1)
            dst = os.path.join(out_dir, name)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(work, dst)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return Result(dst, meta, events)
